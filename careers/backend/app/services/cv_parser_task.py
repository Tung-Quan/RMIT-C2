import logging
from datetime import UTC, datetime

from app.db import models
from app.db.database import SessionLocal
from app.services.cv_parser_client import AICVParserError, parse_cv_document
from app.services.document_text_service import extract_document_text

logger = logging.getLogger(__name__)


async def background_parse_cv(application_id: int, expected_revision: int) -> None:
    """
    Background task to extract CV text and parse it via the AI service.
    Owns its own database sessions and respects ai_cv_parse_revision.
    """
    db = SessionLocal()
    cv_document = None
    try:
        # 1. Fetch application and check revision
        application = (
            db.query(models.JobApplication)
            .filter(models.JobApplication.id == application_id)
            .first()
        )
        if not application:
            logger.warning(f"Application {application_id} not found for parsing.")
            return

        if application.ai_cv_parse_revision != expected_revision:
            logger.info(
                "Application %s revision changed (%s != %s). Skipping CV parse.",
                application_id,
                application.ai_cv_parse_revision,
                expected_revision,
            )
            return

        # 2. Find CV document
        # Fetch attached documents for this application
        attached = (
            db.query(models.JobApplicationDocument)
            .filter(
                models.JobApplicationDocument.job_application_id == application.id,
                models.JobApplicationDocument.document_type == "CV",
            )
            .first()
        )
        if not attached:
            logger.info(f"Application {application_id} has no CV attached. Skipping.")
            application.ai_cv_parse_status = "failed"
            application.ai_cv_parse_error = "No CV document attached."
            db.commit()
            return

        cv_document = (
            db.query(models.Document).filter(models.Document.id == attached.document_id).first()
        )
        if not cv_document:
            logger.warning(f"CV document {attached.document_id} not found.")
            application.ai_cv_parse_status = "failed"
            application.ai_cv_parse_error = "CV document not found in DB."
            db.commit()
            return

        # 3. Mark processing
        application.ai_cv_parse_status = "processing"
        application.ai_cv_parse_error = None
        db.commit()

        # 4. Extract document text using the existing PDF extractor
        extraction_result = extract_document_text(db, cv_document)
        document_text_record = extraction_result.document_text

        if (
            document_text_record.extraction_status != "succeeded"
            or not document_text_record.raw_text
        ):
            extraction_error = document_text_record.error_message or "CV text_unavailable"
            application.ai_cv_parse_status = "failed"
            application.ai_cv_parse_error = f"PDF Extraction failed: {extraction_error}"
            db.commit()
            return

        raw_cv_text = document_text_record.raw_text

    except Exception as e:
        logger.error(f"Error preparing application {application_id} for parsing: {e}")
        return
    finally:
        db.close()

    # 5. Call AI Service (long-running) outside of DB session
    error_msg: str | None = None
    parsed_profile = None
    try:
        parsed_profile = await parse_cv_document(raw_cv_text)
    except AICVParserError as e:
        logger.error(f"AI CV parsing failed for app {application_id}: {str(e)}")
        error_msg = str(e)
    except Exception as e:
        logger.error(f"Unexpected error parsing CV for app {application_id}: {str(e)}")
        error_msg = "An unexpected error occurred during AI parsing."

    # 6. Save result with a fresh DB session
    db_save = SessionLocal()
    try:
        application = (
            db_save.query(models.JobApplication)
            .filter(models.JobApplication.id == application_id)
            .first()
        )
        if not application:
            return

        if application.ai_cv_parse_revision != expected_revision:
            logger.info(
                "Application %s revision changed during CV parsing. Discarding stale result.",
                application_id,
            )
            return

        if error_msg:
            application.ai_cv_parse_status = "failed"
            application.ai_cv_parse_error = error_msg
        elif parsed_profile:
            application.ai_cv_parse_status = "completed"
            application.ai_cv_parsed_profile = parsed_profile
            application.ai_cv_parsed_at = datetime.now(UTC)

        db_save.commit()
    except Exception as e:
        logger.error(f"Error saving parsed result for application {application_id}: {e}")
    finally:
        db_save.close()
