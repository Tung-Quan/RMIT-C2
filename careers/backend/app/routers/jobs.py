from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.metrics import (
    IDEMPOTENCY_DUPLICATE_CONFLICT_TOTAL,
    IDEMPOTENCY_EXECUTION_FAILURE_TOTAL,
)
from app.db import models, schemas
from app.db.conflicts import raise_integrity_conflict, record_integrity_conflict
from app.db.database import get_db
from app.dependencies import require_role
from app.routers.platform_helpers import serialize_job_application_detail, serialize_job_posting
from app.services.idempotency_service import (
    IDEMPOTENCY_RETENTION_DAYS,
    complete_idempotency_record,
    deterministic_request_hash,
    error_response_body,
    idempotency_scope,
    normalize_idempotency_key,
    reserve_idempotency_record,
    utc_now,
)
from app.services.outbox import enqueue_application_submitted_event
from app.services.processing_jobs import enqueue_cv_parse_job

router = APIRouter(tags=["jobs"])
APPLY_OPERATION = "candidate_apply"
APPLY_DUPLICATE_DETAIL = "You have already applied to this job"


def _published_job_query(db: Session):
    return (
        db.query(models.JobPosting)
        .options(joinedload(models.JobPosting.company))
        .filter(models.JobPosting.status == "published")
    )


def _normalize_filter_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@router.get("/jobs", response_model=list[schemas.JobPostingRead])
def list_jobs(
    keyword: str | None = Query(default=None),
    location: str | None = Query(default=None),
    work_mode: str | None = Query(default=None),
    employment_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    keyword = _normalize_filter_value(keyword)
    location = _normalize_filter_value(location)
    work_mode = _normalize_filter_value(work_mode)
    employment_type = _normalize_filter_value(employment_type)

    if work_mode and work_mode not in schemas.JOB_WORK_MODE_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"work_mode must be one of: {', '.join(schemas.JOB_WORK_MODE_VALUES)}",
        )
    if employment_type and employment_type not in schemas.JOB_EMPLOYMENT_TYPE_VALUES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"employment_type must be one of: {', '.join(schemas.JOB_EMPLOYMENT_TYPE_VALUES)}"
            ),
        )

    query = _published_job_query(db).join(models.JobPosting.company)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            (models.JobPosting.title.ilike(pattern))
            | (models.JobPosting.description.ilike(pattern))
            | (models.Company.name.ilike(pattern))
        )
    if location:
        query = query.filter(models.JobPosting.location.ilike(f"%{location}%"))
    if work_mode:
        query = query.filter(models.JobPosting.work_mode == work_mode)
    if employment_type:
        query = query.filter(models.JobPosting.employment_type == employment_type)

    jobs = query.order_by(models.JobPosting.created_at.desc()).all()
    return [serialize_job_posting(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=schemas.JobPostingRead)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = (
        db.query(models.JobPosting)
        .options(joinedload(models.JobPosting.company))
        .filter(
            models.JobPosting.id == job_id,
            models.JobPosting.status == "published",
        )
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize_job_posting(job)


def _apply_request_hash(job_id: int, payload: schemas.JobApplicationCreate) -> str:
    return deterministic_request_hash(
        {
            "operation": APPLY_OPERATION,
            "job_id": job_id,
            "cover_letter_text": payload.cover_letter_text,
            "candidate_note": payload.candidate_note,
            "document_ids": sorted(payload.document_ids),
        }
    )


def _load_job_application_detail(
    db: Session,
    application_id: int,
) -> models.JobApplication | None:
    return (
        db.query(models.JobApplication)
        .options(
            joinedload(models.JobApplication.job_posting).joinedload(models.JobPosting.company),
            joinedload(models.JobApplication.attached_documents).joinedload(
                models.JobApplicationDocument.document
            ),
            joinedload(models.JobApplication.status_history),
        )
        .filter(models.JobApplication.id == application_id)
        .first()
    )


def _create_job_application_in_transaction(
    *,
    db: Session,
    job_id: int,
    payload: schemas.JobApplicationCreate,
    current_user: models.User,
) -> tuple[dict, int]:
    job = (
        db.query(models.JobPosting)
        .options(joinedload(models.JobPosting.company))
        .filter(models.JobPosting.id == job_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "published":
        raise HTTPException(status_code=400, detail="This job is not accepting applications")

    existing = (
        db.query(models.JobApplication)
        .filter(
            models.JobApplication.job_posting_id == job_id,
            models.JobApplication.candidate_user_id == current_user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=APPLY_DUPLICATE_DETAIL,
        )

    if len(set(payload.document_ids)) != len(payload.document_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="document_ids must not contain duplicates",
        )

    documents = (
        db.query(models.Document)
        .filter(
            models.Document.user_id == current_user.id,
            models.Document.id.in_(payload.document_ids),
        )
        .all()
    )
    found_ids = {document.id for document in documents}
    if found_ids != set(payload.document_ids):
        raise HTTPException(
            status_code=400, detail="You can only attach your own existing documents"
        )

    job_application = models.JobApplication(
        job_posting_id=job.id,
        candidate_user_id=current_user.id,
        status="submitted",
        cover_letter_text=payload.cover_letter_text,
        candidate_note=payload.candidate_note,
    )
    db.add(job_application)
    db.flush()

    for document in documents:
        db.add(
            models.JobApplicationDocument(
                job_application_id=job_application.id,
                document_id=document.id,
                document_type=document.document_type,
            )
        )

    db.add(
        models.ApplicationStatusHistory(
            job_application_id=job_application.id,
            old_status=None,
            new_status="submitted",
            changed_by_user_id=current_user.id,
            note="Candidate submitted the application.",
        )
    )
    job_application.ai_cv_parse_status = "pending"
    job_application.ai_cv_parse_revision += 1
    job_application.ai_cv_parse_error = None
    db.flush()

    created = _load_job_application_detail(db, job_application.id)
    if created is None:
        raise HTTPException(status_code=404, detail="Job application not found")
    enqueue_application_submitted_event(
        db,
        application_id=created.id,
        application_version=created.version,
        job_id=created.job_posting_id,
        candidate_user_id=created.candidate_user_id,
        attached_document_ids=[document.id for document in documents],
    )
    enqueue_cv_parse_job(
        db,
        application=created,
        requester_user_id=current_user.id,
    )
    return serialize_job_application_detail(created), created.id


def _store_idempotent_error_after_rollback(
    db: Session,
    *,
    scope: str,
    idempotency_key: str,
    request_hash: str,
    response_status: int,
    response_body: dict,
    operation: str,
) -> JSONResponse | None:
    record = models.IdempotencyRecord(
        scope=scope,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status="completed",
        response_status=response_status,
        response_body=response_body,
        completed_at=utc_now(),
        expires_at=utc_now() + timedelta(days=IDEMPOTENCY_RETENTION_DAYS),
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = reserve_idempotency_record(
            db,
            scope=scope,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            operation=operation,
        )
        if isinstance(replay, JSONResponse):
            return replay
        db.rollback()
        raise
    return None


def _apply_without_idempotency(
    *,
    db: Session,
    job_id: int,
    payload: schemas.JobApplicationCreate,
    current_user: models.User,
) -> dict:
    try:
        response_body, _application_id = _create_job_application_in_transaction(
            db=db,
            job_id=job_id,
            payload=payload,
            current_user=current_user,
        )
        db.commit()
        return response_body
    except IntegrityError as exc:
        raise_integrity_conflict(
            db,
            exc,
            detail=APPLY_DUPLICATE_DETAIL,
            entity_type="job_application",
            operation="apply",
        )
    except Exception:
        db.rollback()
        raise


@router.post(
    "/jobs/{job_id}/apply",
    response_model=schemas.JobApplicationDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def apply_to_job(
    job_id: int,
    payload: schemas.JobApplicationCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    if idempotency_key is None:
        return _apply_without_idempotency(
            db=db,
            job_id=job_id,
            payload=payload,
            current_user=current_user,
        )

    normalized_key = normalize_idempotency_key(idempotency_key)
    scope = idempotency_scope(actor_id=current_user.id, operation=APPLY_OPERATION)
    request_hash = _apply_request_hash(job_id, payload)
    reserved = reserve_idempotency_record(
        db,
        scope=scope,
        idempotency_key=normalized_key,
        request_hash=request_hash,
        operation=APPLY_OPERATION,
    )
    if isinstance(reserved, JSONResponse):
        return reserved

    try:
        response_body, application_id = _create_job_application_in_transaction(
            db=db,
            job_id=job_id,
            payload=payload,
            current_user=current_user,
        )
        response_body = complete_idempotency_record(
            reserved,
            response_status=status.HTTP_201_CREATED,
            response_body=response_body,
            resource_type="job_application",
            resource_id=application_id,
        )
        db.commit()
        return response_body
    except HTTPException as exc:
        complete_idempotency_record(
            reserved,
            response_status=exc.status_code,
            response_body=error_response_body(exc),
        )
        db.commit()
        raise exc
    except IntegrityError as exc:
        db.rollback()
        record_integrity_conflict(entity_type="job_application", operation="apply")
        IDEMPOTENCY_DUPLICATE_CONFLICT_TOTAL.labels(operation=APPLY_OPERATION).inc()
        response_body = {"detail": APPLY_DUPLICATE_DETAIL}
        replay = _store_idempotent_error_after_rollback(
            db,
            scope=scope,
            idempotency_key=normalized_key,
            request_hash=request_hash,
            response_status=status.HTTP_409_CONFLICT,
            response_body=response_body,
            operation=APPLY_OPERATION,
        )
        if replay is not None:
            return replay
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=APPLY_DUPLICATE_DETAIL,
        ) from exc
    except Exception:
        db.rollback()
        IDEMPOTENCY_EXECUTION_FAILURE_TOTAL.labels(
            operation=APPLY_OPERATION,
            error_type="unexpected",
        ).inc()
        raise
