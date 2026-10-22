import asyncio
import logging
import time
from typing import Any

import httpx
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.core.metrics import (
    AI_PROVIDER_DURATION_SECONDS,
    AI_PROVIDER_FAILURES_TOTAL,
    DOCUMENT_PROCESSING_FAILURES_TOTAL,
)
from app.db import models
from app.db.database import SessionLocal
from app.services import document_text_service
from app.services.cv_parser_client import (
    AICVParserError,
    AICVParserInvalidResponseError,
    AICVParserTimeoutError,
    AICVParserUnavailableError,
    parse_cv_document,
)
from app.services.job_parser_client import (
    AIJobParserError,
    AIJobParserInvalidResponseError,
    AIJobParserTimeoutError,
    AIJobParserUnavailableError,
    parse_job_description,
)
from app.services.job_parser_task import is_job_parseable
from app.services.processing_jobs import (
    JOB_TYPE_APPLICATION_RERANK,
    JOB_TYPE_CV_PARSE,
    JOB_TYPE_DOCUMENT_TEXT_EXTRACTION,
    JOB_TYPE_JOB_DESCRIPTION_PARSE,
    ClaimedProcessingJob,
    ProcessingJobError,
    RetryableProcessingJobError,
    bounded_error_message,
    utc_now,
)

logger = logging.getLogger(__name__)


def execute_processing_job(job: ClaimedProcessingJob) -> dict[str, Any]:
    if job.job_type == JOB_TYPE_DOCUMENT_TEXT_EXTRACTION:
        return execute_document_text_extraction(job)
    if job.job_type == JOB_TYPE_JOB_DESCRIPTION_PARSE:
        return execute_job_description_parse(job)
    if job.job_type == JOB_TYPE_CV_PARSE:
        return execute_cv_parse(job)
    if job.job_type == JOB_TYPE_APPLICATION_RERANK:
        return execute_application_rerank(job)
    raise ProcessingJobError("unknown_job_type", "Unknown processing job type.", retryable=False)


def _run_provider_coroutine(operation: str, coroutine) -> dict[str, Any]:
    started = time.monotonic()
    outcome = "success"
    try:
        return asyncio.run(coroutine)
    except (AIJobParserTimeoutError, AICVParserTimeoutError) as exc:
        outcome = "timeout"
        AI_PROVIDER_FAILURES_TOTAL.labels(
            operation=operation,
            error_code="provider_timeout",
            retryable="true",
        ).inc()
        raise RetryableProcessingJobError("provider_timeout", str(exc)) from exc
    except (AIJobParserUnavailableError, AICVParserUnavailableError) as exc:
        outcome = "unavailable"
        AI_PROVIDER_FAILURES_TOTAL.labels(
            operation=operation,
            error_code="provider_unavailable",
            retryable="true",
        ).inc()
        raise RetryableProcessingJobError("provider_unavailable", str(exc)) from exc
    except (AIJobParserInvalidResponseError, AICVParserInvalidResponseError) as exc:
        outcome = "invalid_response"
        AI_PROVIDER_FAILURES_TOTAL.labels(
            operation=operation,
            error_code="provider_invalid_response",
            retryable="false",
        ).inc()
        raise ProcessingJobError("provider_invalid_response", str(exc), retryable=False) from exc
    except (AIJobParserError, AICVParserError) as exc:
        outcome = "provider_error"
        AI_PROVIDER_FAILURES_TOTAL.labels(
            operation=operation,
            error_code="provider_error",
            retryable="true",
        ).inc()
        raise RetryableProcessingJobError("provider_error", str(exc)) from exc
    finally:
        AI_PROVIDER_DURATION_SECONDS.labels(operation=operation, outcome=outcome).observe(
            time.monotonic() - started
        )


def _document_text_result_payload(document_text: models.DocumentText) -> dict[str, Any]:
    return {
        "document_id": document_text.document_id,
        "document_text_id": document_text.id,
        "extraction_status": document_text.extraction_status,
        "text_hash": document_text.text_hash,
    }


def execute_document_text_extraction(job: ClaimedProcessingJob) -> dict[str, Any]:
    document_id = int(job.input_json["document_id"])
    force = bool(job.input_json.get("force", False))
    db = SessionLocal()
    try:
        document = db.get(models.Document, document_id)
        if document is None:
            raise ProcessingJobError("missing_source", "Document not found.", retryable=False)
        document_text = document_text_service.get_or_create_document_text(db, document)
        if document_text.extraction_status == "succeeded" and not force:
            return _document_text_result_payload(document_text)
        document_text.extraction_status = "pending"
        document_text.error_message = None
        file_name = document.file_name
        s3_key = document.s3_key
        db.commit()
    finally:
        db.close()

    data = document_text_service.build_document_text_data(file_name=file_name, s3_key=s3_key)

    save_db = SessionLocal()
    try:
        document = save_db.get(models.Document, document_id)
        if document is None:
            raise ProcessingJobError("missing_source", "Document was deleted.", retryable=False)
        document_text = document_text_service.get_or_create_document_text(save_db, document)
        document_text_service.apply_document_text_data(document_text, data)
        save_db.commit()
        save_db.refresh(document_text)
        result = _document_text_result_payload(document_text)
    finally:
        save_db.close()

    if data.status == "succeeded":
        return result

    error_code = (
        "unsupported_document_type" if data.status == "unsupported" else "document_parse_failed"
    )
    DOCUMENT_PROCESSING_FAILURES_TOTAL.labels(
        operation=JOB_TYPE_DOCUMENT_TEXT_EXTRACTION,
        error_code=error_code,
    ).inc()
    raise ProcessingJobError(
        error_code,
        data.error_message or "Document text extraction failed.",
        retryable=False,
    )


def _load_job_parse_payload(job_id: int, expected_revision: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        job = db.get(models.JobPosting, job_id)
        if job is None:
            raise ProcessingJobError("missing_source", "Job not found.", retryable=False)
        if job.ai_parse_revision != expected_revision:
            raise ProcessingJobError(
                "stale_source_data", "Job parse revision changed.", retryable=False
            )
        if not is_job_parseable(job):
            job.ai_parse_status = "not_started"
            job.ai_parse_error = None
            db.commit()
            raise ProcessingJobError("invalid_source", "Job is not parseable.", retryable=False)
        job.ai_parse_status = "processing"
        job.ai_parse_error = None
        db.commit()
        return {
            "job_title": job.title,
            "description": job.description or "",
            "requirements": job.requirements or "",
            "responsibilities": job.responsibilities or "",
            "employment_type": job.employment_type or "full_time",
            "work_mode": job.work_mode or "onsite",
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "deadline": job.deadline.isoformat() if job.deadline else None,
            "status": "draft",
        }
    finally:
        db.close()


def execute_job_description_parse(job: ClaimedProcessingJob) -> dict[str, Any]:
    job_id = int(job.input_json["job_id"])
    expected_revision = int(job.input_json["expected_revision"])
    raw_payload = _load_job_parse_payload(job_id, expected_revision)
    parsed_profile = _run_provider_coroutine(
        JOB_TYPE_JOB_DESCRIPTION_PARSE,
        parse_job_description(raw_payload),
    )

    db = SessionLocal()
    try:
        posting = db.get(models.JobPosting, job_id)
        if posting is None:
            raise ProcessingJobError("missing_source", "Job was deleted.", retryable=False)
        if posting.ai_parse_revision != expected_revision:
            raise ProcessingJobError(
                "stale_source_data", "Job parse revision changed.", retryable=False
            )
        posting.ai_parse_status = "completed"
        posting.ai_parsed_profile = parsed_profile
        posting.ai_parse_error = None
        posting.ai_parsed_at = utc_now()
        db.commit()
        return {
            "job_id": job_id,
            "ai_parse_revision": expected_revision,
            "status": "completed",
        }
    finally:
        db.close()


def _prepare_cv_parse(
    application_id: int, expected_revision: int
) -> tuple[int, str, str, str | None]:
    db = SessionLocal()
    try:
        application = db.get(models.JobApplication, application_id)
        if application is None:
            raise ProcessingJobError(
                "missing_source", "Job application not found.", retryable=False
            )
        if application.ai_cv_parse_revision != expected_revision:
            raise ProcessingJobError(
                "stale_source_data",
                "Application CV parse revision changed.",
                retryable=False,
            )
        attached = (
            db.query(models.JobApplicationDocument)
            .filter(
                models.JobApplicationDocument.job_application_id == application.id,
                models.JobApplicationDocument.document_type == "CV",
            )
            .first()
        )
        if attached is None:
            application.ai_cv_parse_status = "failed"
            application.ai_cv_parse_error = "No CV document attached."
            db.commit()
            raise ProcessingJobError("missing_source", "No CV document attached.", retryable=False)
        document = db.get(models.Document, attached.document_id)
        if document is None:
            application.ai_cv_parse_status = "failed"
            application.ai_cv_parse_error = "CV document not found."
            db.commit()
            raise ProcessingJobError("missing_source", "CV document not found.", retryable=False)

        application.ai_cv_parse_status = "processing"
        application.ai_cv_parse_error = None
        existing_text = (
            db.query(models.DocumentText)
            .filter(models.DocumentText.document_id == document.id)
            .first()
        )
        raw_text = (
            existing_text.raw_text
            if existing_text
            and existing_text.extraction_status == "succeeded"
            and existing_text.raw_text
            else None
        )
        if existing_text is None:
            document_text_service.get_or_create_document_text(db, document)
        db.commit()
        return document.id, document.file_name, document.s3_key, raw_text
    finally:
        db.close()


def _extract_and_persist_cv_text(document_id: int, file_name: str, s3_key: str) -> str:
    data = document_text_service.build_document_text_data(file_name=file_name, s3_key=s3_key)
    db = SessionLocal()
    try:
        document = db.get(models.Document, document_id)
        if document is None:
            raise ProcessingJobError("missing_source", "CV document was deleted.", retryable=False)
        document_text = document_text_service.get_or_create_document_text(db, document)
        document_text_service.apply_document_text_data(document_text, data)
        db.commit()
        if data.status != "succeeded" or not data.raw_text:
            error_code = (
                "unsupported_document_type"
                if data.status == "unsupported"
                else "document_parse_failed"
            )
            DOCUMENT_PROCESSING_FAILURES_TOTAL.labels(
                operation=JOB_TYPE_CV_PARSE,
                error_code=error_code,
            ).inc()
            raise ProcessingJobError(
                error_code,
                data.error_message or "CV text extraction failed.",
                retryable=False,
            )
        return data.raw_text
    finally:
        db.close()


def execute_cv_parse(job: ClaimedProcessingJob) -> dict[str, Any]:
    application_id = int(job.input_json["application_id"])
    expected_revision = int(job.input_json["expected_revision"])
    document_id, file_name, s3_key, raw_text = _prepare_cv_parse(application_id, expected_revision)
    if raw_text is None:
        raw_text = _extract_and_persist_cv_text(document_id, file_name, s3_key)

    parsed_profile = _run_provider_coroutine(JOB_TYPE_CV_PARSE, parse_cv_document(raw_text))

    db = SessionLocal()
    try:
        application = db.get(models.JobApplication, application_id)
        if application is None:
            raise ProcessingJobError(
                "missing_source", "Job application was deleted.", retryable=False
            )
        if application.ai_cv_parse_revision != expected_revision:
            raise ProcessingJobError(
                "stale_source_data",
                "Application CV parse revision changed.",
                retryable=False,
            )
        application.ai_cv_parse_status = "completed"
        application.ai_cv_parsed_profile = parsed_profile
        application.ai_cv_parse_error = None
        application.ai_cv_parsed_at = utc_now()
        db.commit()
        return {
            "application_id": application_id,
            "document_id": document_id,
            "ai_cv_parse_revision": expected_revision,
            "status": "completed",
        }
    finally:
        db.close()


def _load_rerank_payload(
    rerank_run_id: int,
    expected_job_revision: int,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    db = SessionLocal()
    try:
        run = (
            db.query(models.JobRerankRun)
            .options(joinedload(models.JobRerankRun.job_posting))
            .filter(models.JobRerankRun.id == rerank_run_id)
            .first()
        )
        if run is None:
            raise ProcessingJobError("missing_source", "Rerank run not found.", retryable=False)
        run.status = "processing"
        run.error_message = None
        job = run.job_posting
        if (
            job is None
            or job.ai_parse_status != "completed"
            or not job.ai_parsed_profile
            or job.ai_parse_revision != expected_job_revision
        ):
            db.commit()
            raise ProcessingJobError(
                "stale_source_data", "Job parse data is stale.", retryable=False
            )

        applications = (
            db.query(models.JobApplication)
            .filter(
                models.JobApplication.job_posting_id == job.id,
                models.JobApplication.ai_cv_parse_status == "completed",
                models.JobApplication.ai_cv_parsed_profile.isnot(None),
            )
            .all()
        )
        app_requests = [
            {
                "application_id": application.id,
                "cv_parse_revision": application.ai_cv_parse_revision,
                "candidate_profile": application.ai_cv_parsed_profile,
            }
            for application in applications
        ]
        db.commit()
        if not app_requests:
            return None, []
        return {"job_profile": job.ai_parsed_profile, "applications": app_requests}, app_requests
    finally:
        db.close()


def _call_matching_provider(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    url = f"{settings.AI_SERVICE_BASE_URL.rstrip('/')}/match-applications"
    headers = {}
    if settings.AI_SERVICE_API_KEY:
        headers["X-AI-Service-Key"] = settings.AI_SERVICE_API_KEY

    started = time.monotonic()
    outcome = "success"
    try:
        with httpx.Client(timeout=settings.AI_SERVICE_MATCH_TIMEOUT_SECONDS) as client:
            response = client.post(url, json=payload, headers=headers)
        if response.status_code in {408, 429, 500, 502, 503, 504}:
            outcome = "retryable_http_error"
            AI_PROVIDER_FAILURES_TOTAL.labels(
                operation=JOB_TYPE_APPLICATION_RERANK,
                error_code="provider_unavailable",
                retryable="true",
            ).inc()
            raise RetryableProcessingJobError(
                "provider_unavailable",
                f"AI matching provider returned {response.status_code}.",
            )
        if response.status_code in {400, 401, 403, 404, 422}:
            outcome = "permanent_http_error"
            AI_PROVIDER_FAILURES_TOTAL.labels(
                operation=JOB_TYPE_APPLICATION_RERANK,
                error_code="provider_invalid_response",
                retryable="false",
            ).inc()
            raise ProcessingJobError(
                "provider_invalid_response",
                f"AI matching provider rejected the request with {response.status_code}.",
                retryable=False,
            )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or "results" not in data:
            outcome = "invalid_response"
            AI_PROVIDER_FAILURES_TOTAL.labels(
                operation=JOB_TYPE_APPLICATION_RERANK,
                error_code="provider_invalid_response",
                retryable="false",
            ).inc()
            raise ProcessingJobError(
                "provider_invalid_response",
                "AI matching provider returned malformed data.",
                retryable=False,
            )
        return data
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        outcome = "transport_error"
        AI_PROVIDER_FAILURES_TOTAL.labels(
            operation=JOB_TYPE_APPLICATION_RERANK,
            error_code="provider_unavailable",
            retryable="true",
        ).inc()
        raise RetryableProcessingJobError("provider_unavailable", str(exc)) from exc
    finally:
        AI_PROVIDER_DURATION_SECONDS.labels(
            operation=JOB_TYPE_APPLICATION_RERANK,
            outcome=outcome,
        ).observe(time.monotonic() - started)


def execute_application_rerank(job: ClaimedProcessingJob) -> dict[str, Any]:
    rerank_run_id = int(job.input_json["rerank_run_id"])
    expected_job_revision = int(job.input_json["job_parse_revision"])
    provider_payload, app_requests = _load_rerank_payload(rerank_run_id, expected_job_revision)
    if provider_payload is None:
        db = SessionLocal()
        try:
            run = db.get(models.JobRerankRun, rerank_run_id)
            if run is None:
                raise ProcessingJobError(
                    "missing_source", "Rerank run was deleted.", retryable=False
                )
            run.status = "completed"
            run.model_name = None
            run.completed_at = utc_now()
            db.commit()
            return {
                "rerank_run_id": rerank_run_id,
                "status": "completed",
                "matched_applications": 0,
            }
        finally:
            db.close()

    data = _call_matching_provider(provider_payload)
    app_revision_by_id = {
        int(item["application_id"]): int(item["cv_parse_revision"]) for item in app_requests
    }

    db = SessionLocal()
    try:
        run = (
            db.query(models.JobRerankRun)
            .options(joinedload(models.JobRerankRun.job_posting))
            .filter(models.JobRerankRun.id == rerank_run_id)
            .first()
        )
        if run is None:
            raise ProcessingJobError("missing_source", "Rerank run was deleted.", retryable=False)
        if (
            run.job_posting is None
            or run.job_posting.ai_parse_revision != expected_job_revision
            or run.job_posting.ai_parse_status != "completed"
        ):
            raise ProcessingJobError(
                "stale_source_data", "Job parse data changed.", retryable=False
            )

        results = data.get("results", [])
        applied_count = 0
        for result in results:
            app_id = int(result["application_id"])
            application = db.get(models.JobApplication, app_id)
            if (
                application is None
                or application.ai_cv_parse_revision != app_revision_by_id.get(app_id)
                or application.ai_cv_parse_status != "completed"
            ):
                raise ProcessingJobError(
                    "stale_source_data",
                    "Application CV parse data changed.",
                    retryable=False,
                )
            existing = (
                db.query(models.ApplicationRerankResult)
                .filter(
                    models.ApplicationRerankResult.rerank_run_id == run.id,
                    models.ApplicationRerankResult.job_application_id == app_id,
                )
                .first()
            )
            if existing:
                existing.criterion_results_json = result["criterion_results"]
                existing.global_relevance_score = result.get("global_relevance_score")
            else:
                db.add(
                    models.ApplicationRerankResult(
                        rerank_run_id=run.id,
                        job_application_id=app_id,
                        criterion_results_json=result["criterion_results"],
                        global_relevance_score=result.get("global_relevance_score"),
                    )
                )
            applied_count += 1

        run.status = "completed"
        run.model_name = data.get("model_name")
        run.error_message = None
        run.completed_at = utc_now()
        db.commit()
        return {
            "rerank_run_id": rerank_run_id,
            "status": "completed",
            "matched_applications": applied_count,
            "model_name": run.model_name,
        }
    finally:
        db.close()


def record_processing_failure(
    job: ClaimedProcessingJob,
    *,
    error_code: str,
    error_message: str,
    terminal: bool,
) -> None:
    db = SessionLocal()
    try:
        bounded_message = bounded_error_message(error_message)
        if job.job_type == JOB_TYPE_JOB_DESCRIPTION_PARSE:
            posting = db.get(models.JobPosting, int(job.input_json["job_id"]))
            if posting and posting.ai_parse_revision == job.source_version:
                posting.ai_parse_status = "failed" if terminal else "pending"
                posting.ai_parse_error = bounded_message if terminal else None
        elif job.job_type == JOB_TYPE_CV_PARSE:
            application = db.get(models.JobApplication, int(job.input_json["application_id"]))
            if application and application.ai_cv_parse_revision == job.source_version:
                application.ai_cv_parse_status = "failed" if terminal else "pending"
                application.ai_cv_parse_error = bounded_message if terminal else None
        elif job.job_type == JOB_TYPE_APPLICATION_RERANK:
            run = db.get(models.JobRerankRun, int(job.input_json["rerank_run_id"]))
            if run:
                run.status = "failed" if terminal else "pending"
                run.error_message = bounded_message if terminal else None
                run.completed_at = utc_now() if terminal else None
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "processing_failure_resource_update_failed job_id=%s job_type=%s error_code=%s",
            job.job_id,
            job.job_type,
            error_code,
        )
    finally:
        db.close()
