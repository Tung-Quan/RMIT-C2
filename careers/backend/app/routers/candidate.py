from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session, joinedload

from app.db import models, schemas
from app.db.database import get_db
from app.dependencies import require_role
from app.routers.platform_helpers import (
    get_or_create_candidate_profile,
    serialize_job_application_detail,
    serialize_job_application_summary,
)
from app.services.optimistic_concurrency import (
    VersionedUpdateOutcome,
    versioned_update_exception,
)
from app.services.workflow_commands import execute_application_withdraw_command
from app.services.workflow_idempotency import run_workflow_command_with_optional_idempotency

router = APIRouter(prefix="/candidate", tags=["candidate"])
LEGACY_DEPRECATION_SUNSET = "2026-10-01"


def _candidate_document_query(db: Session, user_id: int):
    return (
        db.query(models.Document)
        .filter(models.Document.user_id == user_id)
        .order_by(models.Document.created_at.desc())
    )


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


def _run_candidate_withdraw_command(
    *,
    db: Session,
    current_user: models.User,
    application_id: int,
    payload: schemas.CandidateWithdrawRequest,
    idempotency_key: str | None,
):
    def execute() -> dict:
        result = execute_application_withdraw_command(
            db,
            application_id=application_id,
            actor_user_id=current_user.id,
            expected_version=payload.expectedVersion,
        )
        if result.outcome != VersionedUpdateOutcome.SUCCESS:
            raise versioned_update_exception(
                result,
                resource_type="application",
                resource_id=application_id,
                expected_version=payload.expectedVersion,
                not_found_detail="Job application not found",
                forbidden_detail="You do not have access to this job application",
                invalid_transition_message="This application can no longer be withdrawn.",
                requested_command="withdraw",
            )
        if not isinstance(result.resource, models.JobApplication):
            raise HTTPException(status_code=404, detail="Application not found")
        return serialize_job_application_detail(result.resource)

    return run_workflow_command_with_optional_idempotency(
        db,
        idempotency_key=idempotency_key,
        resource_type="application",
        resource_id=application_id,
        command="withdraw",
        actor=current_user,
        payload=payload.model_dump(),
        execute=execute,
    )


@router.get("/profile", response_model=schemas.CandidateProfileRead)
def get_candidate_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    return get_or_create_candidate_profile(db, current_user)


@router.put("/profile", response_model=schemas.CandidateProfileRead)
def update_candidate_profile(
    payload: schemas.CandidateProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    profile = get_or_create_candidate_profile(db, current_user)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(profile, field, value)

    if payload.full_name is not None:
        current_user.full_name = payload.full_name

    db.commit()
    db.refresh(profile)
    return profile


@router.get("/documents", response_model=list[schemas.DocumentRead])
def list_candidate_documents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    return _candidate_document_query(db, int(current_user.id)).all()


@router.get("/dashboard", response_model=schemas.CandidateDashboardRead)
def candidate_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    personal_applications = (
        db.query(models.CandidateApplication)
        .filter(models.CandidateApplication.user_id == current_user.id)
        .order_by(models.CandidateApplication.created_at.desc())
        .all()
    )
    job_applications = (
        db.query(models.JobApplication)
        .options(
            joinedload(models.JobApplication.job_posting).joinedload(models.JobPosting.company),
            joinedload(models.JobApplication.attached_documents),
        )
        .filter(models.JobApplication.candidate_user_id == current_user.id)
        .order_by(models.JobApplication.submitted_at.desc())
        .all()
    )
    recent_documents = _candidate_document_query(db, int(current_user.id)).limit(5).all()

    upcoming_deadlines: list[dict] = []
    today = date.today()
    for application in personal_applications:
        if application.deadline and application.deadline >= today:
            upcoming_deadlines.append(
                {
                    "type": "tracker",
                    "label": f"{application.company_name} - {application.position_title}",
                    "deadline": application.deadline,
                    "status": application.application_status,
                }
            )
    for job_application in job_applications:
        deadline = job_application.job_posting.deadline
        if deadline and deadline >= today:
            upcoming_deadlines.append(
                {
                    "type": "job",
                    "label": (
                        f"{job_application.job_posting.company.name} "
                        f"- {job_application.job_posting.title}"
                    ),
                    "deadline": deadline,
                    "status": job_application.status,
                }
            )
    upcoming_deadlines.sort(key=lambda item: item["deadline"])

    return {
        "total_personal_applications": len(personal_applications),
        "total_submitted_job_applications": len(job_applications),
        "recent_documents": recent_documents,
        "upcoming_deadlines": upcoming_deadlines[:5],
        "recent_job_applications": [
            serialize_job_application_summary(application) for application in job_applications[:5]
        ],
    }


@router.get("/job-applications", response_model=list[schemas.JobApplicationSummaryRead])
def list_candidate_job_applications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    applications = (
        db.query(models.JobApplication)
        .options(
            joinedload(models.JobApplication.job_posting).joinedload(models.JobPosting.company),
            joinedload(models.JobApplication.attached_documents),
        )
        .filter(models.JobApplication.candidate_user_id == current_user.id)
        .order_by(models.JobApplication.submitted_at.desc())
        .all()
    )
    return [serialize_job_application_summary(application) for application in applications]


@router.get(
    "/job-applications/{application_id}",
    response_model=schemas.JobApplicationDetailRead,
)
def get_candidate_job_application(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    application = (
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
    if not application:
        raise HTTPException(status_code=404, detail="Job application not found")
    if application.candidate_user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You do not have access to this job application"
        )
    return serialize_job_application_detail(application)


@router.post(
    "/job-applications/{application_id}/withdraw", response_model=schemas.JobApplicationDetailRead
)
def withdraw_candidate_job_application(
    application_id: int,
    payload: schemas.CandidateWithdrawRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    return _run_candidate_withdraw_command(
        db=db,
        current_user=current_user,
        application_id=application_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )


@router.patch(
    "/job-applications/{application_id}/withdraw", response_model=schemas.JobApplicationDetailRead
)
def withdraw_candidate_job_application_legacy(
    application_id: int,
    payload: schemas.CandidateWithdrawRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    replacement = f"POST /candidate/job-applications/{application_id}/withdraw"
    _mark_deprecated(response, replacement=replacement)
    try:
        return _run_candidate_withdraw_command(
            db=db,
            current_user=current_user,
            application_id=application_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )
    except HTTPException as exc:
        raise _with_deprecation_headers(exc, replacement=replacement) from exc
