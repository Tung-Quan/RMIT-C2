import logging
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.db import models, schemas
from app.db.database import get_db
from app.dependencies import require_application_owner, require_role
from app.services.document_text_service import document_text_payload
from app.services.processing_jobs import (
    enqueue_document_text_extraction_job,
    processing_job_payload,
)
from app.services.s3_service import generate_presigned_url, put_bytes_to_s3
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"])


DIRECT_DOCUMENTS_COMPANY = "Personal Documents"
DIRECT_DOCUMENTS_POSITION = "Reusable candidate documents"
DIRECT_DOCUMENTS_DESCRIPTION = (
    "Storage area for documents uploaded directly from candidate job applications."
)
DIRECT_DOCUMENTS_NOTE = (
    "Auto-created to store reusable documents uploaded directly from the job apply page."
)


def get_application_for_document_action(
    db: Session,
    application_id: int,
    current_user: models.User,
) -> models.CandidateApplication:
    return require_application_owner(application_id, db, current_user)


def get_document_for_user(
    db: Session,
    document_id: int,
    current_user: models.User,
) -> models.Document:
    document = db.get(models.Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    application = db.get(models.CandidateApplication, document.application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Document application not found")

    if document.user_id != current_user.id or application.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this document",
        )
    return document


def get_document_for_text_access(
    db: Session,
    document_id: int,
    current_user: models.User,
) -> models.Document:
    document = db.get(models.Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if current_user.role == "admin":
        return document

    # Hiring staff may also use their own ordinary candidate document workspace.
    if document.user_id == current_user.id:
        return get_document_for_user(db, document_id, current_user)

    if current_user.role == "candidate":
        return get_document_for_user(db, document_id, current_user)

    if current_user.role == "hr":
        link = (
            db.query(models.JobApplicationDocument)
            .join(
                models.JobApplication,
                models.JobApplicationDocument.job_application_id == models.JobApplication.id,
            )
            .join(models.JobPosting, models.JobApplication.job_posting_id == models.JobPosting.id)
            .join(models.Company, models.JobPosting.company_id == models.Company.id)
            .filter(
                models.JobApplicationDocument.document_id == document_id,
                models.Company.owner_user_id == current_user.id,
                models.JobApplicationDocument.document_type == "CV",
            )
            .first()
        )
        if link:
            return document
        raise HTTPException(status_code=404, detail="Document not found")

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this document",
    )


def validate_document_type(document_type: str) -> str:
    cleaned = document_type.strip()
    if cleaned not in schemas.DOCUMENT_TYPE_VALUES:
        raise HTTPException(status_code=400, detail="Invalid document type")
    return cleaned


def get_or_create_direct_documents_application(
    db: Session,
    current_user: models.User,
) -> models.CandidateApplication:
    application = (
        db.query(models.CandidateApplication)
        .filter(
            models.CandidateApplication.user_id == current_user.id,
            models.CandidateApplication.company_name == DIRECT_DOCUMENTS_COMPANY,
            models.CandidateApplication.position_title == DIRECT_DOCUMENTS_POSITION,
            models.CandidateApplication.job_description == DIRECT_DOCUMENTS_DESCRIPTION,
        )
        .order_by(models.CandidateApplication.id.asc())
        .first()
    )
    if application:
        return application

    application = models.CandidateApplication(
        user_id=current_user.id,
        company_name=DIRECT_DOCUMENTS_COMPANY,
        position_title=DIRECT_DOCUMENTS_POSITION,
        job_description=DIRECT_DOCUMENTS_DESCRIPTION,
        application_status="Saved",
        deadline=None,
        notes=DIRECT_DOCUMENTS_NOTE,
    )
    db.add(application)
    db.flush()
    return application


async def create_document_record(
    db: Session,
    current_user: models.User,
    application_id: int,
    document_type: str,
    file: UploadFile,
    source: str,
) -> models.Document:
    cleaned_document_type = validate_document_type(document_type)

    storage = StorageService()
    stored = None
    try:
        stored = await storage.save_file(file, int(current_user.id), application_id)
        document = models.Document(
            user_id=current_user.id,
            application_id=application_id,
            document_type=cleaned_document_type,
            file_name=stored.file_name,
            file_url=stored.file_url,
            s3_key=stored.s3_key,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        logger.info(
            "document_uploaded user_id=%s application_id=%s document_id=%s ext=%s source=%s",
            current_user.id,
            application_id,
            document.id,
            Path(document.file_name).suffix.lower(),
            source,
        )
        return document
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        if stored:
            try:
                storage.delete_file(stored.s3_key)
            except Exception:
                logger.exception("document_upload_cleanup_failed s3_key=%s", stored.s3_key)
        logger.exception(
            "document_upload_failed user_id=%s application_id=%s source=%s",
            current_user.id,
            application_id,
            source,
        )
        raise HTTPException(status_code=500, detail="Unable to upload document") from exc


@router.post("/documents/upload")
async def upload_demo_document(file: UploadFile = File(...)):
    """S3 smoke-test route only.

    This endpoint is intentionally not connected to users, applications, or the
    documents table. Use POST /applications/{application_id}/documents for the
    real application document workflow.
    """
    try:
        storage = StorageService()
        file_name, data = await storage.read_validated_upload(file)
        user_id = "demo-user"
        file_key = f"users/{user_id}/documents/{uuid.uuid4()}-{file_name}"
        put_bytes_to_s3(file_key, data, file.content_type)
        download_url = generate_presigned_url(file_key)
        return {
            "message": "File uploaded successfully",
            "s3_key": file_key,
            "download_url": download_url,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("demo_document_upload_failed")
        raise HTTPException(status_code=500, detail="Unable to upload demo document") from exc


@router.post(
    "/applications/{application_id}/documents",
    response_model=schemas.DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    application_id: int,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    get_application_for_document_action(db, application_id, current_user)
    return await create_document_record(
        db,
        current_user,
        application_id,
        document_type,
        file,
        source="tracker_application",
    )


@router.post(
    "/candidate/documents",
    response_model=schemas.DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_candidate_document(
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    application = get_or_create_direct_documents_application(db, current_user)
    return await create_document_record(
        db,
        current_user,
        int(application.id),
        document_type,
        file,
        source="candidate_direct_upload",
    )


@router.get(
    "/applications/{application_id}/documents",
    response_model=list[schemas.DocumentRead],
)
def list_documents(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    get_application_for_document_action(db, application_id, current_user)
    return (
        db.query(models.Document)
        .filter(
            models.Document.application_id == application_id,
            models.Document.user_id == current_user.id,
        )
        .order_by(models.Document.created_at.desc())
        .all()
    )


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    document = get_document_for_user(db, document_id, current_user)
    try:
        StorageService().delete_file(str(document.s3_key))
        db.delete(document)
        db.commit()
        logger.info("document_deleted user_id=%s document_id=%s", current_user.id, document_id)
        return {"message": "Document deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception(
            "document_delete_failed user_id=%s document_id=%s",
            current_user.id,
            document_id,
        )
        raise HTTPException(status_code=500, detail="Unable to delete document") from exc


@router.get("/documents/{document_id}/download-url", response_model=schemas.DocumentDownloadUrl)
def get_document_download_url(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    document = get_document_for_user(db, document_id, current_user)

    try:
        download_url = StorageService().generate_download_url(
            str(document.s3_key),
            fallback_url=str(document.file_url) if document.file_url else None,
        )
        return {
            "document_id": document.id,
            "download_url": download_url,
            "expires_in": 3600,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "document_download_url_failed user_id=%s document_id=%s",
            current_user.id,
            document_id,
        )
        raise HTTPException(status_code=500, detail="Unable to generate download URL") from exc


@router.post(
    "/documents/{document_id}/extract-text",
    response_model=schemas.DocumentTextExtractResponse | schemas.ProcessingJobRead,
)
def extract_document_text_endpoint(
    document_id: int,
    response: Response,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "hr", "admin")),
):
    document = get_document_for_text_access(db, document_id, current_user)
    existing = (
        db.query(models.DocumentText).filter(models.DocumentText.document_id == document.id).first()
    )
    if existing and existing.extraction_status == "succeeded" and not force:
        return document_text_payload(existing, skipped_cached=True)

    job = enqueue_document_text_extraction_job(
        db,
        document=document,
        requester_user_id=current_user.id,
        force=force,
    )
    db.commit()
    db.refresh(job)
    response.status_code = status.HTTP_202_ACCEPTED
    return processing_job_payload(job)


@router.get(
    "/documents/{document_id}/extracted-text-status",
    response_model=schemas.DocumentTextStatusResponse,
)
def get_extracted_text_status(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "hr", "admin")),
):
    get_document_for_text_access(db, document_id, current_user)
    document_text = (
        db.query(models.DocumentText).filter(models.DocumentText.document_id == document_id).first()
    )
    if not document_text:
        raise HTTPException(status_code=404, detail="Document text has not been extracted")
    return document_text


@router.get("/documents/{document_id}/text", response_model=schemas.DocumentTextResponse)
def get_extracted_text(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "hr", "admin")),
):
    get_document_for_text_access(db, document_id, current_user)
    document_text = (
        db.query(models.DocumentText).filter(models.DocumentText.document_id == document_id).first()
    )
    if not document_text:
        raise HTTPException(status_code=404, detail="Document text has not been extracted")
    return document_text
