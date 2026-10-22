import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.metrics import (
    PROCESSING_JOBS_CLAIMED_TOTAL,
    PROCESSING_JOBS_ENQUEUED_TOTAL,
    PROCESSING_JOBS_FAILED_TOTAL,
    PROCESSING_JOBS_LEASE_RECLAIMED_TOTAL,
    PROCESSING_JOBS_RETRIED_TOTAL,
    PROCESSING_JOBS_SUCCEEDED_TOTAL,
    PROCESSING_OLDEST_QUEUED_AGE_SECONDS,
    PROCESSING_QUEUE_DEPTH,
)
from app.db import models

PROCESSING_STATUS_QUEUED = "queued"
PROCESSING_STATUS_RUNNING = "running"
PROCESSING_STATUS_SUCCEEDED = "succeeded"
PROCESSING_STATUS_FAILED = "failed"
PROCESSING_STATUS_CANCELLED = "cancelled"
PROCESSING_ACTIVE_STATUSES = (PROCESSING_STATUS_QUEUED, PROCESSING_STATUS_RUNNING)
PROCESSING_TERMINAL_STATUSES = (
    PROCESSING_STATUS_SUCCEEDED,
    PROCESSING_STATUS_FAILED,
    PROCESSING_STATUS_CANCELLED,
)

JOB_TYPE_DOCUMENT_TEXT_EXTRACTION = "document_text_extraction"
JOB_TYPE_JOB_DESCRIPTION_PARSE = "job_description_parse"
JOB_TYPE_CV_PARSE = "cv_parse"
JOB_TYPE_APPLICATION_RERANK = "application_rerank"
PROCESSING_JOB_TYPES = (
    JOB_TYPE_DOCUMENT_TEXT_EXTRACTION,
    JOB_TYPE_JOB_DESCRIPTION_PARSE,
    JOB_TYPE_CV_PARSE,
    JOB_TYPE_APPLICATION_RERANK,
)

MAX_ERROR_MESSAGE_LENGTH = 512

ProcessingRetryOutcome = Literal["retry", "failed", "missing"]


@dataclass(frozen=True)
class ClaimedProcessingJob:
    job_id: str
    job_type: str
    input_json: dict[str, Any]
    attempts: int
    max_attempts: int
    source_entity_type: str | None
    source_entity_id: str | None
    source_version: int | None
    source_checksum: str | None


class ProcessingJobError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class RetryableProcessingJobError(ProcessingJobError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, retryable=True)


def utc_now() -> datetime:
    return datetime.now(UTC)


def bounded_error_message(error: BaseException | str) -> str:
    message = str(error)
    if len(message) <= MAX_ERROR_MESSAGE_LENGTH:
        return message
    return message[: MAX_ERROR_MESSAGE_LENGTH - 3] + "..."


def processing_job_payload(job: models.AsyncProcessingJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "related_entity_type": job.related_entity_type,
        "related_entity_id": job.related_entity_id,
        "source_entity_type": job.source_entity_type,
        "source_entity_id": job.source_entity_id,
        "source_version": job.source_version,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "available_at": job.available_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "last_error_code": job.last_error_code,
        "last_error_message": job.last_error_message,
        "result": job.result_json,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "version": job.version,
    }


def _deduplication_key(*parts: object) -> str:
    return ":".join(str(part) for part in parts)


def _find_active_related_job(
    db: Session,
    *,
    job_type: str,
    related_entity_type: str,
    related_entity_id: int | str,
    source_version: int | None = None,
) -> models.AsyncProcessingJob | None:
    query = (
        db.query(models.AsyncProcessingJob)
        .filter(
            models.AsyncProcessingJob.job_type == job_type,
            models.AsyncProcessingJob.related_entity_type == related_entity_type,
            models.AsyncProcessingJob.related_entity_id == str(related_entity_id),
            models.AsyncProcessingJob.status.in_(PROCESSING_ACTIVE_STATUSES),
        )
        .order_by(models.AsyncProcessingJob.created_at.desc())
    )
    if source_version is not None:
        query = query.filter(models.AsyncProcessingJob.source_version == source_version)
    return query.first()


def enqueue_processing_job(
    db: Session,
    *,
    job_type: str,
    deduplication_key: str,
    input_json: dict[str, Any],
    owner_user_id: int | None,
    requester_user_id: int | None,
    related_entity_type: str | None,
    related_entity_id: int | str | None,
    source_entity_type: str | None,
    source_entity_id: int | str | None,
    source_version: int | None,
    source_checksum: str | None = None,
    max_attempts: int = 3,
    requeue_failed: bool = True,
    now: datetime | None = None,
) -> models.AsyncProcessingJob:
    job = (
        db.query(models.AsyncProcessingJob)
        .filter(models.AsyncProcessingJob.deduplication_key == deduplication_key)
        .first()
    )
    if job is not None:
        if requeue_failed and job.status == PROCESSING_STATUS_FAILED:
            job.status = PROCESSING_STATUS_QUEUED
            job.attempts = 0
            job.available_at = now or utc_now()
            job.locked_at = None
            job.locked_until = None
            job.locked_by = None
            job.started_at = None
            job.completed_at = None
            job.last_error_code = None
            job.last_error_message = None
            job.version += 1
        return job

    enqueue_time = now or utc_now()
    job = models.AsyncProcessingJob(
        id=str(uuid.uuid4()),
        job_type=job_type,
        status=PROCESSING_STATUS_QUEUED,
        owner_user_id=owner_user_id,
        requester_user_id=requester_user_id,
        related_entity_type=related_entity_type,
        related_entity_id=str(related_entity_id) if related_entity_id is not None else None,
        source_entity_type=source_entity_type,
        source_entity_id=str(source_entity_id) if source_entity_id is not None else None,
        source_version=source_version,
        source_checksum=source_checksum,
        deduplication_key=deduplication_key,
        input_json=input_json,
        attempts=0,
        max_attempts=max_attempts,
        available_at=enqueue_time,
        version=1,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        existing = (
            db.query(models.AsyncProcessingJob)
            .filter(models.AsyncProcessingJob.deduplication_key == deduplication_key)
            .first()
        )
        if existing is not None:
            return existing
        raise
    PROCESSING_JOBS_ENQUEUED_TOTAL.labels(job_type=job_type).inc()
    return job


def enqueue_document_text_extraction_job(
    db: Session,
    *,
    document: models.Document,
    requester_user_id: int,
    force: bool = False,
    max_attempts: int = 3,
) -> models.AsyncProcessingJob:
    active = _find_active_related_job(
        db,
        job_type=JOB_TYPE_DOCUMENT_TEXT_EXTRACTION,
        related_entity_type="document",
        related_entity_id=document.id,
    )
    if active is not None:
        return active

    existing_text = (
        db.query(models.DocumentText).filter(models.DocumentText.document_id == document.id).first()
    )
    source_checksum = existing_text.text_hash if existing_text else None
    dedupe_revision = source_checksum or (
        existing_text.updated_at.isoformat() if existing_text else "initial"
    )
    dedupe_mode = "force" if force else "normal"
    return enqueue_processing_job(
        db,
        job_type=JOB_TYPE_DOCUMENT_TEXT_EXTRACTION,
        deduplication_key=_deduplication_key(
            JOB_TYPE_DOCUMENT_TEXT_EXTRACTION,
            "document",
            document.id,
            dedupe_mode,
            dedupe_revision,
        ),
        input_json={
            "document_id": document.id,
            "force": force,
        },
        owner_user_id=document.user_id,
        requester_user_id=requester_user_id,
        related_entity_type="document",
        related_entity_id=document.id,
        source_entity_type="document",
        source_entity_id=document.id,
        source_version=None,
        source_checksum=source_checksum,
        max_attempts=max_attempts,
    )


def enqueue_job_description_parse_job(
    db: Session,
    *,
    job: models.JobPosting,
    requester_user_id: int,
    max_attempts: int = 3,
) -> models.AsyncProcessingJob:
    active = _find_active_related_job(
        db,
        job_type=JOB_TYPE_JOB_DESCRIPTION_PARSE,
        related_entity_type="job",
        related_entity_id=job.id,
        source_version=job.ai_parse_revision,
    )
    if active is not None:
        return active

    return enqueue_processing_job(
        db,
        job_type=JOB_TYPE_JOB_DESCRIPTION_PARSE,
        deduplication_key=_deduplication_key(
            JOB_TYPE_JOB_DESCRIPTION_PARSE,
            "job",
            job.id,
            job.ai_parse_revision,
        ),
        input_json={
            "job_id": job.id,
            "expected_revision": job.ai_parse_revision,
        },
        owner_user_id=job.created_by_user_id,
        requester_user_id=requester_user_id,
        related_entity_type="job",
        related_entity_id=job.id,
        source_entity_type="job",
        source_entity_id=job.id,
        source_version=job.ai_parse_revision,
        max_attempts=max_attempts,
    )


def enqueue_cv_parse_job(
    db: Session,
    *,
    application: models.JobApplication,
    requester_user_id: int,
    max_attempts: int = 3,
) -> models.AsyncProcessingJob:
    active = _find_active_related_job(
        db,
        job_type=JOB_TYPE_CV_PARSE,
        related_entity_type="job_application",
        related_entity_id=application.id,
        source_version=application.ai_cv_parse_revision,
    )
    if active is not None:
        return active

    return enqueue_processing_job(
        db,
        job_type=JOB_TYPE_CV_PARSE,
        deduplication_key=_deduplication_key(
            JOB_TYPE_CV_PARSE,
            "job_application",
            application.id,
            application.ai_cv_parse_revision,
        ),
        input_json={
            "application_id": application.id,
            "expected_revision": application.ai_cv_parse_revision,
        },
        owner_user_id=application.candidate_user_id,
        requester_user_id=requester_user_id,
        related_entity_type="job_application",
        related_entity_id=application.id,
        source_entity_type="job_application",
        source_entity_id=application.id,
        source_version=application.ai_cv_parse_revision,
        max_attempts=max_attempts,
    )


def enqueue_application_rerank_job(
    db: Session,
    *,
    rerank_run: models.JobRerankRun,
    requester_user_id: int,
    job_parse_revision: int,
    max_attempts: int = 3,
) -> models.AsyncProcessingJob:
    return enqueue_processing_job(
        db,
        job_type=JOB_TYPE_APPLICATION_RERANK,
        deduplication_key=_deduplication_key(
            JOB_TYPE_APPLICATION_RERANK,
            "rerank_run",
            rerank_run.id,
        ),
        input_json={
            "rerank_run_id": rerank_run.id,
            "job_id": rerank_run.job_posting_id,
            "job_parse_revision": job_parse_revision,
        },
        owner_user_id=rerank_run.created_by_user_id,
        requester_user_id=requester_user_id,
        related_entity_type="job_rerank_run",
        related_entity_id=rerank_run.id,
        source_entity_type="job",
        source_entity_id=rerank_run.job_posting_id,
        source_version=job_parse_revision,
        max_attempts=max_attempts,
    )


def claim_processing_jobs(
    db: Session,
    *,
    worker_id: str,
    batch_size: int,
    lease_seconds: int,
    now: datetime | None = None,
) -> list[ClaimedProcessingJob]:
    if batch_size <= 0:
        return []
    claim_time = now or utc_now()
    claim_query = (
        select(
            models.AsyncProcessingJob.id,
            models.AsyncProcessingJob.status,
            models.AsyncProcessingJob.job_type,
        )
        .where(
            or_(
                and_(
                    models.AsyncProcessingJob.status == PROCESSING_STATUS_QUEUED,
                    models.AsyncProcessingJob.available_at <= claim_time,
                ),
                and_(
                    models.AsyncProcessingJob.status == PROCESSING_STATUS_RUNNING,
                    models.AsyncProcessingJob.locked_until <= claim_time,
                ),
            )
        )
        .order_by(
            models.AsyncProcessingJob.available_at.asc(),
            models.AsyncProcessingJob.created_at.asc(),
            models.AsyncProcessingJob.id.asc(),
        )
        .limit(batch_size)
    )
    if db.get_bind().dialect.name == "postgresql":
        claim_query = claim_query.with_for_update(skip_locked=True)

    rows = db.execute(claim_query).mappings().all()
    if not rows:
        return []

    job_ids = [str(row["id"]) for row in rows]
    previous_status_by_id = {str(row["id"]): str(row["status"]) for row in rows}
    job_type_by_id = {str(row["id"]): str(row["job_type"]) for row in rows}
    locked_until = claim_time + timedelta(seconds=lease_seconds)
    db.execute(
        update(models.AsyncProcessingJob)
        .where(models.AsyncProcessingJob.id.in_(job_ids))
        .values(
            status=PROCESSING_STATUS_RUNNING,
            locked_at=claim_time,
            locked_until=locked_until,
            locked_by=worker_id,
            started_at=claim_time,
            version=models.AsyncProcessingJob.version + 1,
        )
    )
    jobs = (
        db.execute(
            select(models.AsyncProcessingJob).where(models.AsyncProcessingJob.id.in_(job_ids))
        )
        .scalars()
        .all()
    )
    jobs_by_id = {job.id: job for job in jobs}
    claimed: list[ClaimedProcessingJob] = []
    for job_id in job_ids:
        job = jobs_by_id[job_id]
        PROCESSING_JOBS_CLAIMED_TOTAL.labels(job_type=job.job_type).inc()
        if previous_status_by_id[job_id] == PROCESSING_STATUS_RUNNING:
            PROCESSING_JOBS_LEASE_RECLAIMED_TOTAL.labels(job_type=job_type_by_id[job_id]).inc()
        claimed.append(
            ClaimedProcessingJob(
                job_id=job.id,
                job_type=job.job_type,
                input_json=job.input_json,
                attempts=job.attempts,
                max_attempts=job.max_attempts,
                source_entity_type=job.source_entity_type,
                source_entity_id=job.source_entity_id,
                source_version=job.source_version,
                source_checksum=job.source_checksum,
            )
        )
    return claimed


def mark_processing_job_succeeded(
    db: Session,
    *,
    job_id: str,
    result_json: dict[str, Any],
    now: datetime | None = None,
) -> bool:
    job = db.get(models.AsyncProcessingJob, job_id)
    if job is None:
        return False
    complete_time = now or utc_now()
    job.status = PROCESSING_STATUS_SUCCEEDED
    job.result_json = result_json
    job.locked_at = None
    job.locked_until = None
    job.locked_by = None
    job.completed_at = complete_time
    job.last_error_code = None
    job.last_error_message = None
    job.version += 1
    PROCESSING_JOBS_SUCCEEDED_TOTAL.labels(job_type=job.job_type).inc()
    return True


def compute_retry_delay(
    *,
    attempts: int,
    base_delay_seconds: int,
    max_delay_seconds: int,
) -> timedelta:
    raw_delay = min(max_delay_seconds, base_delay_seconds * (2 ** max(attempts - 1, 0)))
    jitter = random.uniform(0, min(raw_delay * 0.1, 30))
    return timedelta(seconds=min(max_delay_seconds, raw_delay + jitter))


def mark_processing_job_retry_or_failed(
    db: Session,
    *,
    job_id: str,
    error_code: str,
    error_message: str,
    retryable: bool,
    base_delay_seconds: int,
    max_delay_seconds: int,
    now: datetime | None = None,
) -> ProcessingRetryOutcome:
    job = db.get(models.AsyncProcessingJob, job_id)
    if job is None:
        return "missing"
    failure_time = now or utc_now()
    job.attempts += 1
    job.locked_at = None
    job.locked_until = None
    job.locked_by = None
    job.last_error_code = error_code
    job.last_error_message = bounded_error_message(error_message)
    job.version += 1
    if not retryable or job.attempts >= job.max_attempts:
        job.status = PROCESSING_STATUS_FAILED
        job.available_at = failure_time
        job.completed_at = failure_time
        PROCESSING_JOBS_FAILED_TOTAL.labels(
            job_type=job.job_type,
            error_code=error_code,
        ).inc()
        return "failed"

    job.status = PROCESSING_STATUS_QUEUED
    job.available_at = failure_time + compute_retry_delay(
        attempts=job.attempts,
        base_delay_seconds=base_delay_seconds,
        max_delay_seconds=max_delay_seconds,
    )
    PROCESSING_JOBS_RETRIED_TOTAL.labels(
        job_type=job.job_type,
        error_code=error_code,
    ).inc()
    return "retry"


def refresh_processing_gauges(db: Session, *, now: datetime | None = None) -> None:
    snapshot_time = now or utc_now()
    for job_type in PROCESSING_JOB_TYPES:
        PROCESSING_QUEUE_DEPTH.labels(job_type=job_type).set(0)
        PROCESSING_OLDEST_QUEUED_AGE_SECONDS.labels(job_type=job_type).set(0)

    count_rows = (
        db.execute(
            select(
                models.AsyncProcessingJob.job_type,
                func.count(models.AsyncProcessingJob.id),
            )
            .where(models.AsyncProcessingJob.status == PROCESSING_STATUS_QUEUED)
            .group_by(models.AsyncProcessingJob.job_type)
        )
        .tuples()
        .all()
    )
    for job_type, count in count_rows:
        PROCESSING_QUEUE_DEPTH.labels(job_type=job_type).set(count)

    oldest_rows = (
        db.execute(
            select(
                models.AsyncProcessingJob.job_type,
                func.min(models.AsyncProcessingJob.available_at),
            )
            .where(models.AsyncProcessingJob.status == PROCESSING_STATUS_QUEUED)
            .group_by(models.AsyncProcessingJob.job_type)
        )
        .tuples()
        .all()
    )
    for job_type, oldest_available_at in oldest_rows:
        if oldest_available_at is None:
            continue
        if oldest_available_at.tzinfo is None:
            oldest_available_at = oldest_available_at.replace(tzinfo=UTC)
        age = max(0.0, (snapshot_time - oldest_available_at).total_seconds())
        PROCESSING_OLDEST_QUEUED_AGE_SECONDS.labels(job_type=job_type).set(age)


def get_authorized_processing_job(
    db: Session,
    *,
    job_id: str,
    current_user: models.User,
) -> models.AsyncProcessingJob:
    job = db.get(models.AsyncProcessingJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Processing job not found"
        )
    if current_user.role == "admin":
        return job
    if job.owner_user_id == current_user.id or job.requester_user_id == current_user.id:
        return job
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Processing job not found",
    )
