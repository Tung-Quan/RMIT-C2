from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, joinedload

from app.db import models, schemas
from app.db.database import get_db
from app.dependencies import (
    require_hr_job_application,
    require_job_owner,
    require_role,
)
from app.routers.platform_helpers import (
    serialize_attached_document,
    serialize_company,
    serialize_job_application_detail,
    serialize_job_posting,
)
from app.services.document_text_service import document_text_payload
from app.services.job_parser_task import is_job_parseable
from app.services.optimistic_concurrency import (
    VersionedUpdateOutcome,
    VersionedUpdateResult,
    invalid_state_transition_detail,
    update_job_with_version,
    versioned_update_exception,
)
from app.services.processing_jobs import (
    JOB_TYPE_APPLICATION_RERANK,
    PROCESSING_ACTIVE_STATUSES,
    enqueue_application_rerank_job,
    enqueue_cv_parse_job,
    enqueue_document_text_extraction_job,
    enqueue_job_description_parse_job,
    processing_job_payload,
)
from app.services.storage_service import StorageService
from app.services.workflow_commands import (
    APPLICATION_ADVANCE_TRANSITIONS,
    JobCommand,
    execute_application_advance_command,
    execute_application_reject_command,
    execute_delete_draft_job_command,
    execute_job_status_command,
)
from app.services.workflow_idempotency import run_workflow_command_with_optional_idempotency

router = APIRouter(prefix="/hr", tags=["hr"])

LEGACY_DEPRECATION_SUNSET = "2026-10-01"

JOB_COMMAND_INVALID_MESSAGES = {
    "publish": "A job can be published only from draft.",
    "close": "A job can be closed only from published.",
    "reopen": "A job can be reopened only from closed.",
    "archive": "A job can be archived only from published.",
    "delete_draft": "Only draft jobs with no applications can be permanently deleted.",
}

APPLICATION_COMMAND_INVALID_MESSAGES = {
    "advance": "This application cannot advance to the requested stage from its current state.",
    "reject": "This application can no longer be rejected.",
}


def _mark_deprecated(response: Response, *, replacement: str) -> None:
    for header, value in _deprecation_headers(replacement=replacement).items():
        response.headers[header] = value


def _deprecation_headers(*, replacement: str) -> dict[str, str]:
    return {
        "Deprecation": "true",
        "Sunset": LEGACY_DEPRECATION_SUNSET,
        "X-Replaced-By": replacement,
    }


def _with_deprecation_headers(exc: HTTPException, *, replacement: str) -> HTTPException:
    headers = dict(exc.headers or {})
    headers.update(_deprecation_headers(replacement=replacement))
    exc.headers = headers
    return exc


def _raise_job_command_failure(
    result: VersionedUpdateResult,
    *,
    job_id: int,
    expected_version: int,
    command: str,
) -> None:
    raise versioned_update_exception(
        result,
        resource_type="job",
        resource_id=job_id,
        expected_version=expected_version,
        not_found_detail="Job not found",
        forbidden_detail="You do not have access to this job",
        invalid_transition_message=JOB_COMMAND_INVALID_MESSAGES[command],
        requested_command=command,
    )


def _raise_application_command_failure(
    result: VersionedUpdateResult,
    *,
    application_id: int,
    expected_version: int,
    command: str,
) -> None:
    raise versioned_update_exception(
        result,
        resource_type="application",
        resource_id=application_id,
        expected_version=expected_version,
        not_found_detail="Job application not found",
        forbidden_detail="You do not have access to this job application",
        invalid_transition_message=APPLICATION_COMMAND_INVALID_MESSAGES[command],
        requested_command=command,
    )


def _run_hr_job_status_command(
    *,
    db: Session,
    current_user: models.User,
    job_id: int,
    payload: schemas.JobCommandRequest,
    command: JobCommand,
    idempotency_key: str | None,
):
    def execute() -> dict:
        result = execute_job_status_command(
            db,
            job_id=job_id,
            owner_user_id=current_user.id,
            expected_version=payload.expectedVersion,
            command=command,
        )
        if result.outcome != VersionedUpdateOutcome.SUCCESS:
            _raise_job_command_failure(
                result,
                job_id=job_id,
                expected_version=payload.expectedVersion,
                command=command,
            )
        if not isinstance(result.resource, models.JobPosting):
            raise HTTPException(status_code=404, detail="Job not found")
        return serialize_job_posting(result.resource)

    return run_workflow_command_with_optional_idempotency(
        db,
        idempotency_key=idempotency_key,
        resource_type="job",
        resource_id=job_id,
        command=command,
        actor=current_user,
        payload=payload.model_dump(),
        execute=execute,
    )


def _run_delete_draft_job_command(
    *,
    db: Session,
    current_user: models.User,
    job_id: int,
    expected_version: int,
    idempotency_key: str | None,
):
    def execute() -> dict:
        result = execute_delete_draft_job_command(
            db,
            job_id=job_id,
            owner_user_id=current_user.id,
            expected_version=expected_version,
        )
        if result.outcome != VersionedUpdateOutcome.SUCCESS:
            _raise_job_command_failure(
                result,
                job_id=job_id,
                expected_version=expected_version,
                command="delete_draft",
            )
        terminal_version = result.current_version or expected_version + 1
        return {
            "id": job_id,
            "status": "deleted",
            "version": terminal_version,
            "message": "Draft job deleted",
        }

    return run_workflow_command_with_optional_idempotency(
        db,
        idempotency_key=idempotency_key,
        resource_type="job",
        resource_id=job_id,
        command="delete_draft",
        actor=current_user,
        payload={"expectedVersion": expected_version},
        execute=execute,
    )


def _run_hr_application_advance_command(
    *,
    db: Session,
    current_user: models.User,
    application_id: int,
    payload: schemas.ApplicationAdvanceRequest,
    idempotency_key: str | None,
):
    def execute() -> dict:
        result = execute_application_advance_command(
            db,
            application_id=application_id,
            actor_user_id=current_user.id,
            expected_version=payload.expectedVersion,
            target_stage=payload.targetStage,
            note=payload.note,
            include_candidate=True,
        )
        if result.outcome != VersionedUpdateOutcome.SUCCESS:
            _raise_application_command_failure(
                result,
                application_id=application_id,
                expected_version=payload.expectedVersion,
                command="advance",
            )
        if not isinstance(result.resource, models.JobApplication):
            raise HTTPException(status_code=404, detail="Application not found")
        return serialize_job_application_detail(result.resource, include_candidate=True)

    return run_workflow_command_with_optional_idempotency(
        db,
        idempotency_key=idempotency_key,
        resource_type="application",
        resource_id=application_id,
        command="advance",
        actor=current_user,
        payload=payload.model_dump(),
        execute=execute,
    )


def _run_hr_application_reject_command(
    *,
    db: Session,
    current_user: models.User,
    application_id: int,
    payload: schemas.ApplicationRejectRequest,
    idempotency_key: str | None,
):
    def execute() -> dict:
        result = execute_application_reject_command(
            db,
            application_id=application_id,
            actor_user_id=current_user.id,
            expected_version=payload.expectedVersion,
            reason=payload.reason,
            include_candidate=True,
        )
        if result.outcome != VersionedUpdateOutcome.SUCCESS:
            _raise_application_command_failure(
                result,
                application_id=application_id,
                expected_version=payload.expectedVersion,
                command="reject",
            )
        if not isinstance(result.resource, models.JobApplication):
            raise HTTPException(status_code=404, detail="Application not found")
        return serialize_job_application_detail(result.resource, include_candidate=True)

    return run_workflow_command_with_optional_idempotency(
        db,
        idempotency_key=idempotency_key,
        resource_type="application",
        resource_id=application_id,
        command="reject",
        actor=current_user,
        payload=payload.model_dump(),
        execute=execute,
    )


def _get_hr_company_or_404(db: Session, current_user: models.User) -> models.Company:
    company = (
        db.query(models.Company).filter(models.Company.owner_user_id == current_user.id).first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.get("/dashboard", response_model=schemas.HRDashboardRead)
def hr_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    company = (
        db.query(models.Company).filter(models.Company.owner_user_id == current_user.id).first()
    )
    if not company:
        return {
            "company": None,
            "total_jobs": 0,
            "published_jobs": 0,
            "total_applicants": 0,
            "recent_applications": [],
        }

    jobs = db.query(models.JobPosting).filter(models.JobPosting.company_id == company.id).all()
    job_ids = [job.id for job in jobs]
    applications = []
    if job_ids:
        applications = (
            db.query(models.JobApplication)
            .options(
                joinedload(models.JobApplication.candidate_user),
                joinedload(models.JobApplication.attached_documents),
            )
            .filter(models.JobApplication.job_posting_id.in_(job_ids))
            .order_by(models.JobApplication.submitted_at.desc())
            .all()
        )

    recent_applications = []
    for application in applications[:5]:
        candidate = application.candidate_user
        recent_applications.append(
            {
                "id": application.id,
                "candidate_user_id": application.candidate_user_id,
                "candidate_name": candidate.full_name or candidate.email,
                "candidate_email": candidate.email,
                "status": application.status,
                "version": application.version,
                "submitted_at": application.submitted_at,
                "attached_documents_count": len(application.attached_documents),
            }
        )

    return {
        "company": serialize_company(company),
        "total_jobs": len(jobs),
        "published_jobs": sum(1 for job in jobs if job.status == "published"),
        "total_applicants": len(applications),
        "recent_applications": recent_applications,
    }


@router.post("/jobs", response_model=schemas.JobPostingRead, status_code=status.HTTP_201_CREATED)
def create_hr_job(
    payload: schemas.JobPostingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    company = _get_hr_company_or_404(db, current_user)
    job = models.JobPosting(
        company_id=company.id,
        created_by_user_id=current_user.id,
        **payload.model_dump(),
    )

    if is_job_parseable(job):
        job.ai_parse_status = "pending"
        job.ai_parse_revision = 1

    db.add(job)
    db.flush()

    if job.ai_parse_status == "pending":
        enqueue_job_description_parse_job(
            db,
            job=job,
            requester_user_id=current_user.id,
        )

    db.commit()
    db.refresh(job)

    loaded_job = (
        db.query(models.JobPosting)
        .options(joinedload(models.JobPosting.company))
        .filter(models.JobPosting.id == job.id)
        .first()
    )
    assert loaded_job is not None
    return serialize_job_posting(loaded_job)


@router.get("/jobs", response_model=list[schemas.JobPostingRead])
def list_hr_jobs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    company = _get_hr_company_or_404(db, current_user)
    jobs = (
        db.query(models.JobPosting)
        .options(joinedload(models.JobPosting.company))
        .filter(models.JobPosting.company_id == company.id)
        .order_by(models.JobPosting.created_at.desc())
        .all()
    )
    return [serialize_job_posting(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=schemas.JobPostingRead)
def get_hr_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    job = require_job_owner(job_id, db, current_user)
    loaded = (
        db.query(models.JobPosting)
        .options(joinedload(models.JobPosting.company))
        .filter(models.JobPosting.id == job.id)
        .first()
    )
    assert loaded is not None
    return serialize_job_posting(loaded)


@router.put("/jobs/{job_id}", response_model=schemas.JobPostingRead)
def update_hr_job(
    job_id: int,
    payload: schemas.JobPostingUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    if payload.status is not None:
        require_job_owner(job_id, db, current_user)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=invalid_state_transition_detail(
                resource_type="job",
                resource_id=job_id,
                message="Use workflow command endpoints to change job status.",
                requested_command="update",
            ),
        )
    updates = payload.model_dump(exclude_unset=True, exclude={"expectedVersion", "status"})
    existing_job = require_job_owner(job_id, db, current_user)
    parse_relevant_fields = {"title", "description", "requirements", "responsibilities"}
    needs_reparse = any(
        field in updates and updates[field] != getattr(existing_job, field)
        for field in parse_relevant_fields
    )
    result = update_job_with_version(
        db,
        job_id=job_id,
        owner_user_id=current_user.id,
        expected_version=payload.expectedVersion,
        updates=updates,
        operation="update",
    )
    if result.outcome != VersionedUpdateOutcome.SUCCESS:
        db.rollback()
        raise versioned_update_exception(
            result,
            resource_type="job",
            resource_id=job_id,
            expected_version=payload.expectedVersion,
            not_found_detail="Job not found",
            forbidden_detail="You do not have access to this job",
            invalid_transition_message="This job transition is not allowed.",
        )
    if not isinstance(result.resource, models.JobPosting):
        raise HTTPException(status_code=404, detail="Job not found")
    if needs_reparse:
        if is_job_parseable(result.resource):
            result.resource.ai_parse_revision += 1
            result.resource.ai_parse_status = "pending"
            result.resource.ai_parse_error = None
            result.resource.ai_parsed_profile = None
            result.resource.ai_parsed_at = None
            enqueue_job_description_parse_job(
                db,
                job=result.resource,
                requester_user_id=current_user.id,
            )
        else:
            result.resource.ai_parse_status = "not_started"
            result.resource.ai_parsed_profile = None
            result.resource.ai_parse_error = None
            result.resource.ai_parsed_at = None
    db.commit()
    return serialize_job_posting(result.resource)


@router.post("/jobs/{job_id}/publish", response_model=schemas.JobPostingRead)
def publish_hr_job(
    job_id: int,
    payload: schemas.JobCommandRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    return _run_hr_job_status_command(
        db=db,
        current_user=current_user,
        job_id=job_id,
        payload=payload,
        command="publish",
        idempotency_key=idempotency_key,
    )


@router.post("/jobs/{job_id}/close", response_model=schemas.JobPostingRead)
def close_hr_job(
    job_id: int,
    payload: schemas.JobCommandRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    return _run_hr_job_status_command(
        db=db,
        current_user=current_user,
        job_id=job_id,
        payload=payload,
        command="close",
        idempotency_key=idempotency_key,
    )


@router.post("/jobs/{job_id}/reopen", response_model=schemas.JobPostingRead)
def reopen_hr_job(
    job_id: int,
    payload: schemas.JobCommandRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    return _run_hr_job_status_command(
        db=db,
        current_user=current_user,
        job_id=job_id,
        payload=payload,
        command="reopen",
        idempotency_key=idempotency_key,
    )


@router.post("/jobs/{job_id}/archive", response_model=schemas.JobPostingRead)
def archive_hr_job(
    job_id: int,
    payload: schemas.JobCommandRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    return _run_hr_job_status_command(
        db=db,
        current_user=current_user,
        job_id=job_id,
        payload=payload,
        command="archive",
        idempotency_key=idempotency_key,
    )


@router.post("/jobs/{job_id}/delete-draft", response_model=schemas.JobDeleteResult)
def delete_draft_hr_job(
    job_id: int,
    payload: schemas.JobCommandRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    return _run_delete_draft_job_command(
        db=db,
        current_user=current_user,
        job_id=job_id,
        expected_version=payload.expectedVersion,
        idempotency_key=idempotency_key,
    )


@router.delete("/jobs/{job_id}", response_model=schemas.JobDeleteResult)
def delete_hr_job(
    job_id: int,
    response: Response,
    expected_version: int = Query(alias="expectedVersion", ge=1),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    replacement = f"POST /hr/jobs/{job_id}/delete-draft"
    _mark_deprecated(response, replacement=replacement)
    try:
        return _run_delete_draft_job_command(
            db=db,
            current_user=current_user,
            job_id=job_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )
    except HTTPException as exc:
        raise _with_deprecation_headers(exc, replacement=replacement) from exc


@router.patch("/jobs/{job_id}/status", response_model=schemas.JobPostingRead)
def update_hr_job_status(
    job_id: int,
    payload: schemas.JobPostingStatusUpdate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    replacement = f"POST /hr/jobs/{job_id}/publish|close|reopen"
    _mark_deprecated(response, replacement=replacement)
    job = require_job_owner(job_id, db, current_user)
    if payload.status == "published":
        command: JobCommand = "reopen" if job.status == "closed" else "publish"
    elif payload.status == "closed":
        command = "close"
    else:
        raise _with_deprecation_headers(
            HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=invalid_state_transition_detail(
                    resource_type="job",
                    resource_id=job_id,
                    message=(
                        "Use publish, close, or reopen workflow commands for job status changes."
                    ),
                    current_status=job.status,
                    requested_command="status_change",
                ),
            ),
            replacement=replacement,
        )
    try:
        return _run_hr_job_status_command(
            db=db,
            current_user=current_user,
            job_id=job_id,
            payload=schemas.JobCommandRequest(expectedVersion=payload.expectedVersion),
            command=command,
            idempotency_key=idempotency_key,
        )
    except HTTPException as exc:
        raise _with_deprecation_headers(exc, replacement=replacement) from exc


@router.get("/jobs/{job_id}/applications", response_model=list[schemas.HRApplicantSummaryRead])
def list_hr_job_applications(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    job = require_job_owner(job_id, db, current_user)
    applications = (
        db.query(models.JobApplication)
        .options(
            joinedload(models.JobApplication.candidate_user),
            joinedload(models.JobApplication.attached_documents),
        )
        .filter(models.JobApplication.job_posting_id == job.id)
        .order_by(models.JobApplication.submitted_at.desc())
        .all()
    )
    return [
        {
            "id": application.id,
            "candidate_user_id": application.candidate_user_id,
            "candidate_name": application.candidate_user.full_name
            or application.candidate_user.email,
            "candidate_email": application.candidate_user.email,
            "status": application.status,
            "version": application.version,
            "submitted_at": application.submitted_at,
            "attached_documents_count": len(application.attached_documents),
        }
        for application in applications
    ]


@router.get("/applications/{application_id}", response_model=schemas.HRJobApplicationDetailRead)
def get_hr_application_detail(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    application = require_hr_job_application(application_id, db, current_user)
    loaded = (
        db.query(models.JobApplication)
        .options(
            joinedload(models.JobApplication.job_posting).joinedload(models.JobPosting.company),
            joinedload(models.JobApplication.candidate_user).joinedload(
                models.User.candidate_profile
            ),
            joinedload(models.JobApplication.attached_documents).joinedload(
                models.JobApplicationDocument.document
            ),
            joinedload(models.JobApplication.status_history),
        )
        .filter(models.JobApplication.id == application.id)
        .first()
    )
    assert loaded is not None
    return serialize_job_application_detail(loaded, include_candidate=True)


@router.post(
    "/applications/{application_id}/advance",
    response_model=schemas.HRJobApplicationDetailRead,
)
def advance_hr_application(
    application_id: int,
    payload: schemas.ApplicationAdvanceRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    return _run_hr_application_advance_command(
        db=db,
        current_user=current_user,
        application_id=application_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/applications/{application_id}/reject",
    response_model=schemas.HRJobApplicationDetailRead,
)
def reject_hr_application(
    application_id: int,
    payload: schemas.ApplicationRejectRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    return _run_hr_application_reject_command(
        db=db,
        current_user=current_user,
        application_id=application_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )


@router.patch(
    "/applications/{application_id}/status",
    response_model=schemas.HRJobApplicationDetailRead,
)
def update_hr_application_status(
    application_id: int,
    payload: schemas.StatusUpdateRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    replacement = f"POST /hr/applications/{application_id}/advance|reject"
    _mark_deprecated(response, replacement=replacement)
    if payload.status == "withdrawn":
        raise _with_deprecation_headers(
            HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=invalid_state_transition_detail(
                    resource_type="application",
                    resource_id=application_id,
                    message="HR cannot set status to withdrawn.",
                    requested_command="status_change",
                ),
            ),
            replacement=replacement,
        )
    if payload.status == "rejected":
        try:
            return _run_hr_application_reject_command(
                db=db,
                current_user=current_user,
                application_id=application_id,
                payload=schemas.ApplicationRejectRequest(
                    expectedVersion=payload.expectedVersion,
                    reason=payload.note,
                ),
                idempotency_key=idempotency_key,
            )
        except HTTPException as exc:
            raise _with_deprecation_headers(exc, replacement=replacement) from exc
    if payload.status in APPLICATION_ADVANCE_TRANSITIONS:
        try:
            return _run_hr_application_advance_command(
                db=db,
                current_user=current_user,
                application_id=application_id,
                payload=schemas.ApplicationAdvanceRequest(
                    expectedVersion=payload.expectedVersion,
                    targetStage=payload.status,
                    note=payload.note,
                ),
                idempotency_key=idempotency_key,
            )
        except HTTPException as exc:
            raise _with_deprecation_headers(exc, replacement=replacement) from exc
    raise _with_deprecation_headers(
        HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=invalid_state_transition_detail(
                resource_type="application",
                resource_id=application_id,
                message="Use advance or reject workflow commands for application status changes.",
                requested_command="status_change",
            ),
        ),
        replacement=replacement,
    )


@router.get(
    "/applications/{application_id}/documents",
    response_model=list[schemas.AttachedDocumentRead],
)
def list_hr_application_documents(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    application = require_hr_job_application(application_id, db, current_user)
    loaded = (
        db.query(models.JobApplication)
        .options(
            joinedload(models.JobApplication.attached_documents).joinedload(
                models.JobApplicationDocument.document
            )
        )
        .filter(models.JobApplication.id == application.id)
        .first()
    )
    assert loaded is not None
    return [serialize_attached_document(link) for link in loaded.attached_documents]


@router.get("/documents/{document_id}/download-url", response_model=schemas.DocumentDownloadUrl)
def get_hr_document_download_url(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    link = (
        db.query(models.JobApplicationDocument)
        .join(
            models.JobApplication,
            models.JobApplicationDocument.job_application_id == models.JobApplication.id,
        )
        .join(
            models.JobPosting,
            models.JobApplication.job_posting_id == models.JobPosting.id,
        )
        .join(models.Company, models.JobPosting.company_id == models.Company.id)
        .options(joinedload(models.JobApplicationDocument.document))
        .filter(
            models.JobApplicationDocument.document_id == document_id,
            models.Company.owner_user_id == current_user.id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Document not found")

    download_url = StorageService().generate_download_url(
        link.document.s3_key,
        fallback_url=link.document.file_url,
    )
    return {
        "document_id": link.document.id,
        "download_url": download_url,
        "expires_in": 3600,
    }


@router.post(
    "/jobs/{job_id}/applicants/extract-text",
    response_model=schemas.BulkApplicantTextExtractionEnqueueResponse,
)
def extract_text_for_job_applicants(
    job_id: int,
    response: Response,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    owned_job = require_job_owner(job_id, db, current_user)
    applications = (
        db.query(models.JobApplication)
        .options(
            joinedload(models.JobApplication.attached_documents).joinedload(
                models.JobApplicationDocument.document
            ),
        )
        .filter(models.JobApplication.job_posting_id == owned_job.id)
        .all()
    )

    documents_by_id: dict[int, models.Document] = {}
    for application in applications:
        for link in application.attached_documents:
            if link.document_type == "CV" and link.document:
                documents_by_id[link.document_id] = link.document

    queued = 0
    skipped_cached = 0
    results = []
    for document in documents_by_id.values():
        existing = (
            db.query(models.DocumentText)
            .filter(models.DocumentText.document_id == document.id)
            .first()
        )
        if existing and existing.extraction_status == "succeeded" and not force:
            skipped_cached += 1
            results.append(document_text_payload(existing, skipped_cached=True))
            continue
        processing_job = enqueue_document_text_extraction_job(
            db,
            document=document,
            requester_user_id=current_user.id,
            force=force,
        )
        queued += 1
        results.append(processing_job_payload(processing_job))

    db.commit()
    for item in results:
        if "job_type" in item:
            queued_job = db.get(models.AsyncProcessingJob, item["id"])
            if queued_job is not None:
                item.update(processing_job_payload(queued_job))
    if queued:
        response.status_code = status.HTTP_202_ACCEPTED

    return {
        "job_id": owned_job.id,
        "total_documents": len(documents_by_id),
        "queued": queued,
        "skipped_cached": skipped_cached,
        "results": results,
    }


@router.post(
    "/jobs/{job_id}/parse",
    response_model=schemas.JobPostingProcessingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def manual_reparse_hr_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    job = require_job_owner(job_id, db, current_user)

    if not is_job_parseable(job):
        raise HTTPException(
            status_code=400,
            detail=(
                "Job is not parseable. It must have a title, description, "
                "and at least one requirement or responsibility."
            ),
        )

    if job.ai_parse_status not in {"pending", "processing"}:
        job.ai_parse_revision += 1
        job.ai_parse_status = "pending"
        job.ai_parse_error = None
        job.ai_parsed_profile = None
        job.ai_parsed_at = None

    processing_job = enqueue_job_description_parse_job(
        db,
        job=job,
        requester_user_id=current_user.id,
    )
    db.commit()
    db.refresh(job)
    db.refresh(processing_job)

    refreshed = (
        db.query(models.JobPosting)
        .options(joinedload(models.JobPosting.company))
        .filter(models.JobPosting.id == job.id)
        .first()
    )
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job": serialize_job_posting(refreshed),
        "processing_job": processing_job_payload(processing_job),
    }


@router.post(
    "/applications/{application_id}/parse-cv",
    response_model=schemas.HRJobApplicationProcessingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def manual_reparse_hr_application_cv(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    application = require_hr_job_application(application_id, db, current_user)

    # Check if a CV is attached
    attached = (
        db.query(models.JobApplicationDocument)
        .filter(
            models.JobApplicationDocument.job_application_id == application.id,
            models.JobApplicationDocument.document_type == "CV",
        )
        .first()
    )
    if not attached:
        raise HTTPException(
            status_code=400, detail="No CV document is attached to this application."
        )

    if application.ai_cv_parse_status not in ("pending", "processing"):
        application.ai_cv_parse_revision += 1
        application.ai_cv_parse_status = "pending"
        application.ai_cv_parse_error = None
        application.ai_cv_parsed_profile = None
        application.ai_cv_parsed_at = None

    processing_job = enqueue_cv_parse_job(
        db,
        application=application,
        requester_user_id=current_user.id,
    )
    db.commit()
    db.refresh(processing_job)

    loaded = (
        db.query(models.JobApplication)
        .options(
            joinedload(models.JobApplication.job_posting).joinedload(models.JobPosting.company),
            joinedload(models.JobApplication.candidate_user).joinedload(
                models.User.candidate_profile
            ),
            joinedload(models.JobApplication.attached_documents).joinedload(
                models.JobApplicationDocument.document
            ),
            joinedload(models.JobApplication.status_history),
        )
        .filter(models.JobApplication.id == application.id)
        .first()
    )
    if loaded is None:
        raise HTTPException(status_code=404, detail="Application not found")

    return {
        "application": serialize_job_application_detail(loaded, include_candidate=True),
        "processing_job": processing_job_payload(processing_job),
    }


@router.post(
    "/jobs/{job_id}/rerank",
    response_model=schemas.JobRerankRunProcessingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_job_rerank(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    job = require_job_owner(job_id, db, current_user)

    if job.ai_parse_status != "completed" or not job.ai_parsed_profile:
        raise HTTPException(status_code=400, detail="Job must be parsed by AI before reranking.")

    rerank_run = (
        db.query(models.JobRerankRun)
        .filter(
            models.JobRerankRun.job_posting_id == job.id,
            models.JobRerankRun.created_by_user_id == current_user.id,
            models.JobRerankRun.status.in_(("pending", "processing")),
        )
        .order_by(models.JobRerankRun.created_at.desc())
        .first()
    )
    if rerank_run is None:
        rerank_run = models.JobRerankRun(
            job_posting_id=job.id,
            created_by_user_id=current_user.id,
            status="pending",
        )
        db.add(rerank_run)
        db.flush()

    processing_job = (
        db.query(models.AsyncProcessingJob)
        .filter(
            models.AsyncProcessingJob.job_type == JOB_TYPE_APPLICATION_RERANK,
            models.AsyncProcessingJob.related_entity_type == "job_rerank_run",
            models.AsyncProcessingJob.related_entity_id == str(rerank_run.id),
            models.AsyncProcessingJob.status.in_(PROCESSING_ACTIVE_STATUSES),
        )
        .first()
    )
    if processing_job is None:
        processing_job = enqueue_application_rerank_job(
            db,
            rerank_run=rerank_run,
            requester_user_id=current_user.id,
            job_parse_revision=job.ai_parse_revision,
        )
    db.commit()
    db.refresh(rerank_run)
    db.refresh(processing_job)

    return {
        "rerank_run": rerank_run,
        "processing_job": processing_job_payload(processing_job),
    }


@router.get("/jobs/{job_id}/reranks", response_model=list[schemas.JobRerankRunRead])
def list_job_reranks(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    job = require_job_owner(job_id, db, current_user)
    runs = (
        db.query(models.JobRerankRun)
        .options(joinedload(models.JobRerankRun.application_results))
        .filter(models.JobRerankRun.job_posting_id == job.id)
        .order_by(models.JobRerankRun.created_at.desc())
        .all()
    )
    return runs
