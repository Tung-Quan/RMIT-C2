from typing import Any, Literal, cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.metrics import WORKFLOW_COMMAND_TOTAL
from app.db import models
from app.services.optimistic_concurrency import (
    ActorKind,
    VersionedUpdateOutcome,
    VersionedUpdateResult,
)
from app.services.outbox import (
    enqueue_application_workflow_event,
    enqueue_job_workflow_event,
)

JobCommand = Literal["publish", "close", "reopen", "archive"]
ApplicationCommand = Literal["advance", "reject", "withdraw"]
ApplicationAdvanceTarget = Literal["under_review", "shortlisted", "interview", "offered"]

JOB_COMMAND_TRANSITIONS: dict[JobCommand, tuple[set[str], str]] = {
    "publish": ({"draft"}, "published"),
    "close": ({"published"}, "closed"),
    "reopen": ({"closed"}, "published"),
    "archive": ({"published"}, "closed"),
}

APPLICATION_ADVANCE_TRANSITIONS: dict[ApplicationAdvanceTarget, tuple[set[str], str]] = {
    "under_review": ({"submitted"}, "under_review"),
    "shortlisted": ({"under_review"}, "shortlisted"),
    "interview": ({"shortlisted"}, "interview"),
    "offered": ({"interview"}, "offered"),
}

APPLICATION_REJECT_SOURCES = {"submitted", "under_review", "shortlisted", "interview"}
APPLICATION_WITHDRAW_SOURCES = {"submitted", "under_review", "shortlisted", "interview"}


def record_workflow_outcome(
    *,
    resource_type: str,
    command: str,
    outcome: VersionedUpdateOutcome | Literal["replay"],
) -> None:
    outcome_value = outcome.value if isinstance(outcome, VersionedUpdateOutcome) else outcome
    WORKFLOW_COMMAND_TOTAL.labels(
        resource_type=resource_type,
        command=command,
        outcome=outcome_value,
    ).inc()


def _load_job(db: Session, job_id: int) -> models.JobPosting | None:
    return (
        db.query(models.JobPosting)
        .options(joinedload(models.JobPosting.company))
        .filter(models.JobPosting.id == job_id)
        .first()
    )


def _load_application(
    db: Session,
    application_id: int,
    *,
    include_candidate: bool,
) -> models.JobApplication | None:
    options = [
        joinedload(models.JobApplication.job_posting).joinedload(models.JobPosting.company),
        joinedload(models.JobApplication.attached_documents).joinedload(
            models.JobApplicationDocument.document
        ),
        joinedload(models.JobApplication.status_history),
    ]
    if include_candidate:
        options.append(
            joinedload(models.JobApplication.candidate_user).joinedload(
                models.User.candidate_profile
            )
        )
    return (
        db.query(models.JobApplication)
        .options(*options)
        .filter(models.JobApplication.id == application_id)
        .first()
    )


def _record_and_return(
    result: VersionedUpdateResult,
    *,
    resource_type: str,
    command: str,
) -> VersionedUpdateResult:
    record_workflow_outcome(
        resource_type=resource_type,
        command=command,
        outcome=result.outcome,
    )
    return result


def _classify_job_command_failure(
    db: Session,
    *,
    job_id: int,
    owner_user_id: int,
    expected_version: int,
    allowed_source_states: set[str],
    command: str,
) -> VersionedUpdateResult:
    row = (
        db.execute(
            select(
                models.JobPosting.version,
                models.JobPosting.status,
                models.Company.owner_user_id,
            )
            .join(models.Company, models.JobPosting.company_id == models.Company.id)
            .where(models.JobPosting.id == job_id)
        )
        .mappings()
        .first()
    )
    if row is None:
        return _record_and_return(
            VersionedUpdateResult(outcome=VersionedUpdateOutcome.NOT_FOUND),
            resource_type="job",
            command=command,
        )
    if row["owner_user_id"] != owner_user_id:
        return _record_and_return(
            VersionedUpdateResult(outcome=VersionedUpdateOutcome.UNAUTHORIZED),
            resource_type="job",
            command=command,
        )
    if row["version"] != expected_version:
        return _record_and_return(
            VersionedUpdateResult(
                outcome=VersionedUpdateOutcome.STALE,
                current_version=row["version"],
                current_status=row["status"],
            ),
            resource_type="job",
            command=command,
        )
    if row["status"] not in allowed_source_states:
        return _record_and_return(
            VersionedUpdateResult(
                outcome=VersionedUpdateOutcome.INVALID_TRANSITION,
                current_version=row["version"],
                current_status=row["status"],
            ),
            resource_type="job",
            command=command,
        )
    return _record_and_return(
        VersionedUpdateResult(
            outcome=VersionedUpdateOutcome.STALE,
            current_version=row["version"],
            current_status=row["status"],
        ),
        resource_type="job",
        command=command,
    )


def execute_job_status_command(
    db: Session,
    *,
    job_id: int,
    owner_user_id: int,
    expected_version: int,
    command: JobCommand,
) -> VersionedUpdateResult:
    allowed_source_states, result_status = JOB_COMMAND_TRANSITIONS[command]
    from_status = sorted(allowed_source_states)[0]
    authorized_company_ids = select(models.Company.id).where(
        models.Company.owner_user_id == owner_user_id
    )
    row = (
        db.execute(
            update(models.JobPosting)
            .where(
                models.JobPosting.id == job_id,
                models.JobPosting.company_id.in_(authorized_company_ids),
                models.JobPosting.version == expected_version,
                models.JobPosting.status.in_(allowed_source_states),
            )
            .values(
                status=result_status,
                version=models.JobPosting.version + 1,
                updated_at=func.now(),
            )
            .returning(
                models.JobPosting.id,
                models.JobPosting.version,
                models.JobPosting.company_id,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return _classify_job_command_failure(
            db,
            job_id=job_id,
            owner_user_id=owner_user_id,
            expected_version=expected_version,
            allowed_source_states=allowed_source_states,
            command=command,
        )

    enqueue_job_workflow_event(
        db,
        command_name=command,
        job_id=job_id,
        aggregate_version=row["version"],
        from_status=from_status,
        to_status=result_status,
        company_id=row["company_id"],
    )

    job = _load_job(db, job_id)
    if job is None:
        raise RuntimeError("Updated job could not be reloaded")
    return _record_and_return(
        VersionedUpdateResult(
            outcome=VersionedUpdateOutcome.SUCCESS,
            resource=job,
            current_version=row["version"],
            current_status=result_status,
        ),
        resource_type="job",
        command=command,
    )


def _classify_delete_draft_failure(
    db: Session,
    *,
    job_id: int,
    owner_user_id: int,
    expected_version: int,
) -> VersionedUpdateResult:
    has_applications = (
        select(models.JobApplication.id)
        .where(models.JobApplication.job_posting_id == job_id)
        .exists()
    )
    row = (
        db.execute(
            select(
                models.JobPosting.version,
                models.JobPosting.status,
                models.Company.owner_user_id,
                has_applications.label("has_applications"),
            )
            .join(models.Company, models.JobPosting.company_id == models.Company.id)
            .where(models.JobPosting.id == job_id)
        )
        .mappings()
        .first()
    )
    if row is None:
        return _record_and_return(
            VersionedUpdateResult(outcome=VersionedUpdateOutcome.NOT_FOUND),
            resource_type="job",
            command="delete_draft",
        )
    if row["owner_user_id"] != owner_user_id:
        return _record_and_return(
            VersionedUpdateResult(outcome=VersionedUpdateOutcome.UNAUTHORIZED),
            resource_type="job",
            command="delete_draft",
        )
    if row["version"] != expected_version:
        return _record_and_return(
            VersionedUpdateResult(
                outcome=VersionedUpdateOutcome.STALE,
                current_version=row["version"],
                current_status=row["status"],
            ),
            resource_type="job",
            command="delete_draft",
        )
    if row["status"] != "draft" or row["has_applications"]:
        return _record_and_return(
            VersionedUpdateResult(
                outcome=VersionedUpdateOutcome.INVALID_TRANSITION,
                current_version=row["version"],
                current_status=row["status"],
            ),
            resource_type="job",
            command="delete_draft",
        )
    return _record_and_return(
        VersionedUpdateResult(
            outcome=VersionedUpdateOutcome.STALE,
            current_version=row["version"],
            current_status=row["status"],
        ),
        resource_type="job",
        command="delete_draft",
    )


def execute_delete_draft_job_command(
    db: Session,
    *,
    job_id: int,
    owner_user_id: int,
    expected_version: int,
) -> VersionedUpdateResult:
    authorized_company_ids = select(models.Company.id).where(
        models.Company.owner_user_id == owner_user_id
    )
    has_applications = (
        select(models.JobApplication.id)
        .where(models.JobApplication.job_posting_id == job_id)
        .exists()
    )
    row = (
        db.execute(
            delete(models.JobPosting)
            .where(
                models.JobPosting.id == job_id,
                models.JobPosting.company_id.in_(authorized_company_ids),
                models.JobPosting.version == expected_version,
                models.JobPosting.status == "draft",
                ~has_applications,
            )
            .returning(
                models.JobPosting.id,
                models.JobPosting.version,
                models.JobPosting.company_id,
                models.JobPosting.status,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return _classify_delete_draft_failure(
            db,
            job_id=job_id,
            owner_user_id=owner_user_id,
            expected_version=expected_version,
        )
    terminal_version = expected_version + 1
    enqueue_job_workflow_event(
        db,
        command_name="delete_draft",
        job_id=job_id,
        aggregate_version=terminal_version,
        from_status=row["status"],
        to_status="deleted",
        company_id=row["company_id"],
    )
    return _record_and_return(
        VersionedUpdateResult(
            outcome=VersionedUpdateOutcome.SUCCESS,
            current_version=terminal_version,
            current_status="deleted",
        ),
        resource_type="job",
        command="delete_draft",
    )


def _application_authorization_conditions(
    *,
    application_id: int,
    actor_user_id: int,
    actor_kind: ActorKind,
) -> list[Any]:
    conditions: list[Any] = [models.JobApplication.id == application_id]
    if actor_kind == "candidate":
        conditions.append(models.JobApplication.candidate_user_id == actor_user_id)
    else:
        authorized_job_ids = (
            select(models.JobPosting.id)
            .join(models.Company, models.JobPosting.company_id == models.Company.id)
            .where(models.Company.owner_user_id == actor_user_id)
        )
        conditions.append(models.JobApplication.job_posting_id.in_(authorized_job_ids))
    return conditions


def _read_authorized_application_status(
    db: Session,
    *,
    application_id: int,
    actor_user_id: int,
    actor_kind: ActorKind,
) -> str | None:
    row = (
        db.execute(
            select(models.JobApplication.status).where(
                *_application_authorization_conditions(
                    application_id=application_id,
                    actor_user_id=actor_user_id,
                    actor_kind=actor_kind,
                )
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return cast(str, row["status"])


def _classify_application_command_failure(
    db: Session,
    *,
    application_id: int,
    actor_user_id: int,
    actor_kind: ActorKind,
    expected_version: int,
    allowed_source_states: set[str],
    command: str,
) -> VersionedUpdateResult:
    row = (
        db.execute(
            select(
                models.JobApplication.version,
                models.JobApplication.status,
                models.JobApplication.candidate_user_id,
                models.Company.owner_user_id,
            )
            .join(models.JobPosting, models.JobApplication.job_posting_id == models.JobPosting.id)
            .join(models.Company, models.JobPosting.company_id == models.Company.id)
            .where(models.JobApplication.id == application_id)
        )
        .mappings()
        .first()
    )
    if row is None:
        return _record_and_return(
            VersionedUpdateResult(outcome=VersionedUpdateOutcome.NOT_FOUND),
            resource_type="application",
            command=command,
        )
    if actor_kind == "candidate" and row["candidate_user_id"] != actor_user_id:
        return _record_and_return(
            VersionedUpdateResult(outcome=VersionedUpdateOutcome.UNAUTHORIZED),
            resource_type="application",
            command=command,
        )
    if actor_kind == "hr" and row["owner_user_id"] != actor_user_id:
        return _record_and_return(
            VersionedUpdateResult(outcome=VersionedUpdateOutcome.UNAUTHORIZED),
            resource_type="application",
            command=command,
        )
    if row["version"] != expected_version:
        return _record_and_return(
            VersionedUpdateResult(
                outcome=VersionedUpdateOutcome.STALE,
                current_version=row["version"],
                current_status=row["status"],
            ),
            resource_type="application",
            command=command,
        )
    if row["status"] not in allowed_source_states:
        return _record_and_return(
            VersionedUpdateResult(
                outcome=VersionedUpdateOutcome.INVALID_TRANSITION,
                current_version=row["version"],
                current_status=row["status"],
            ),
            resource_type="application",
            command=command,
        )
    return _record_and_return(
        VersionedUpdateResult(
            outcome=VersionedUpdateOutcome.STALE,
            current_version=row["version"],
            current_status=row["status"],
        ),
        resource_type="application",
        command=command,
    )


def execute_application_status_command(
    db: Session,
    *,
    application_id: int,
    actor_user_id: int,
    actor_kind: ActorKind,
    expected_version: int,
    command: ApplicationCommand,
    result_status: str,
    allowed_source_states: set[str],
    note: str | None,
    include_candidate: bool = False,
) -> VersionedUpdateResult:
    old_status = _read_authorized_application_status(
        db,
        application_id=application_id,
        actor_user_id=actor_user_id,
        actor_kind=actor_kind,
    )
    conditions = _application_authorization_conditions(
        application_id=application_id,
        actor_user_id=actor_user_id,
        actor_kind=actor_kind,
    )
    conditions.extend(
        [
            models.JobApplication.version == expected_version,
            models.JobApplication.status.in_(allowed_source_states),
        ]
    )
    row = (
        db.execute(
            update(models.JobApplication)
            .where(*conditions)
            .values(
                status=result_status,
                version=models.JobApplication.version + 1,
                updated_at=func.now(),
            )
            .returning(
                models.JobApplication.id,
                models.JobApplication.version,
                models.JobApplication.job_posting_id,
                models.JobApplication.candidate_user_id,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return _classify_application_command_failure(
            db,
            application_id=application_id,
            actor_user_id=actor_user_id,
            actor_kind=actor_kind,
            expected_version=expected_version,
            allowed_source_states=allowed_source_states,
            command=command,
        )
    if old_status is None:
        raise RuntimeError("Updated application old status could not be determined")

    db.add(
        models.ApplicationStatusHistory(
            job_application_id=application_id,
            old_status=old_status,
            new_status=result_status,
            changed_by_user_id=actor_user_id,
            note=note,
        )
    )
    db.flush()
    enqueue_application_workflow_event(
        db,
        command_name=command,
        application_id=application_id,
        aggregate_version=row["version"],
        from_status=old_status,
        to_status=result_status,
        job_id=row["job_posting_id"],
        candidate_user_id=row["candidate_user_id"],
    )

    application = _load_application(
        db,
        application_id,
        include_candidate=include_candidate,
    )
    if application is None:
        raise RuntimeError("Updated application could not be reloaded")
    return _record_and_return(
        VersionedUpdateResult(
            outcome=VersionedUpdateOutcome.SUCCESS,
            resource=application,
            current_version=row["version"],
            current_status=result_status,
        ),
        resource_type="application",
        command=command,
    )


def execute_application_advance_command(
    db: Session,
    *,
    application_id: int,
    actor_user_id: int,
    expected_version: int,
    target_stage: ApplicationAdvanceTarget,
    note: str | None,
    include_candidate: bool = False,
) -> VersionedUpdateResult:
    allowed_source_states, result_status = APPLICATION_ADVANCE_TRANSITIONS[target_stage]
    return execute_application_status_command(
        db,
        application_id=application_id,
        actor_user_id=actor_user_id,
        actor_kind="hr",
        expected_version=expected_version,
        command="advance",
        result_status=result_status,
        allowed_source_states=allowed_source_states,
        note=note,
        include_candidate=include_candidate,
    )


def execute_application_reject_command(
    db: Session,
    *,
    application_id: int,
    actor_user_id: int,
    expected_version: int,
    reason: str | None,
    include_candidate: bool = False,
) -> VersionedUpdateResult:
    return execute_application_status_command(
        db,
        application_id=application_id,
        actor_user_id=actor_user_id,
        actor_kind="hr",
        expected_version=expected_version,
        command="reject",
        result_status="rejected",
        allowed_source_states=APPLICATION_REJECT_SOURCES,
        note=reason,
        include_candidate=include_candidate,
    )


def execute_application_withdraw_command(
    db: Session,
    *,
    application_id: int,
    actor_user_id: int,
    expected_version: int,
) -> VersionedUpdateResult:
    return execute_application_status_command(
        db,
        application_id=application_id,
        actor_user_id=actor_user_id,
        actor_kind="candidate",
        expected_version=expected_version,
        command="withdraw",
        result_status="withdrawn",
        allowed_source_states=APPLICATION_WITHDRAW_SOURCES,
        note="Candidate withdrew the application.",
    )
