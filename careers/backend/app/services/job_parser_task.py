import logging
from datetime import UTC, datetime

from app.db import models
from app.db.database import SessionLocal
from app.services.job_parser_client import AIJobParserError, parse_job_description

logger = logging.getLogger(__name__)


def is_job_parseable(job: models.JobPosting) -> bool:
    """Helper to determine if a job has enough meaningful content to parse."""
    if not job.title or not job.title.strip():
        return False
    if not job.description or not job.description.strip():
        return False

    has_reqs = bool(job.requirements and job.requirements.strip())
    has_resps = bool(job.responsibilities and job.responsibilities.strip())

    # We require at least some structured or unstructured content
    # to be worth sending to the LLM.
    if not has_reqs and not has_resps:
        return False

    return True


async def background_parse_job(job_id: int, expected_revision: int) -> None:
    """
    Background task to parse a job description via the AI service.
    Owns its own database sessions and respects ai_parse_revision.
    """
    db = SessionLocal()
    try:
        # 1. Fetch job and check revision
        job = db.query(models.JobPosting).filter(models.JobPosting.id == job_id).first()
        if not job:
            logger.warning(f"Job {job_id} not found for parsing.")
            return

        if job.ai_parse_revision != expected_revision:
            logger.info(
                "Job %s revision changed (%s != %s). Skipping parse.",
                job_id,
                job.ai_parse_revision,
                expected_revision,
            )
            return

        # 2. Mark processing
        job.ai_parse_status = "processing"
        job.ai_parse_error = None
        db.commit()

        # Build payload while we have the job open
        raw_payload = {
            "job_title": job.title,
            "description": job.description or "",
            "requirements": job.requirements or "",
            "responsibilities": job.responsibilities or "",
            "employment_type": job.employment_type or "full_time",
            "work_mode": job.work_mode or "onsite",
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "deadline": job.deadline.isoformat() if job.deadline else None,
            "status": "draft",  # The parser schema expects this, even if irrelevant
        }
    except Exception as e:
        logger.error(f"Error reading job {job_id} for parsing: {e}")
        return
    finally:
        db.close()

    # 3. Call AI Service (long-running) outside of DB session
    error_msg = None
    parsed_profile = None
    try:
        parsed_profile = await parse_job_description(raw_payload)
    except AIJobParserError as e:
        logger.error(f"AI parsing failed for job {job_id}: {str(e)}")
        error_msg = str(e)
    except Exception as e:
        logger.error(f"Unexpected error parsing job {job_id}: {str(e)}")
        error_msg = "An unexpected error occurred during AI parsing."

    # 4. Save result with a fresh DB session
    db_save = SessionLocal()
    try:
        job = db_save.query(models.JobPosting).filter(models.JobPosting.id == job_id).first()
        if not job:
            return

        if job.ai_parse_revision != expected_revision:
            logger.info(f"Job {job_id} revision changed during parsing. Discarding stale result.")
            return

        if error_msg:
            job.ai_parse_status = "failed"
            job.ai_parse_error = error_msg
        elif parsed_profile:
            job.ai_parse_status = "completed"
            job.ai_parsed_profile = parsed_profile
            job.ai_parsed_at = datetime.now(UTC)

        db_save.commit()
    except Exception as e:
        logger.error(f"Error saving parsed result for job {job_id}: {e}")
    finally:
        db_save.close()
