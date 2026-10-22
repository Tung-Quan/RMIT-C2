from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import func, insert, literal, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.metrics import OPTIMISTIC_CONCURRENCY_TOTAL
from app.db import models

ActorKind = Literal["hr", "candidate"]


class VersionedUpdateOutcome(StrEnum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    STALE = "stale"
    INVALID_TRANSITION = "invalid_transition"
    UNAUTHORIZED = "unauthorized"


@dataclass(frozen=True)
class VersionedUpdateResult:
    outcome: VersionedUpdateOutcome
    resource: models.JobPosting | models.JobApplication | None = None
    current_version: int | None = None
    current_status: str | None = None


def stale_version_detail(
    *,
    resource_type: str,
    resource_id: int,
    expected_version: int,
    current_version: int,
) -> dict[str, Any]:
    return {
        "code": "stale_version",
        "message": "The resource was changed by another request.",
        "resourceType": resource_type,
        "resourceId": resource_id,
        "expectedVersion": expected_version,
        "currentVersion": current_version,
    }


def invalid_state_transition_detail(
    *,
    resource_type: str,
    resource_id: int,
    message: str,
    current_status: str | None = None,
    current_state: str | None = None,
    requested_command: str | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "code": "invalid_state_transition",
        "message": message,
        "resourceType": resource_type,
        "resourceId": resource_id,
    }
    if current_state is not None:
        detail["currentState"] = current_state
    if current_status is not None:
        detail["currentStatus"] = current_status
        detail.setdefault("currentState", current_status)
    if requested_command is not None:
        detail["requestedCommand"] = requested_command
    return detail


def versioned_update_exception(
    result: VersionedUpdateResult,
    *,
    resource_type: str,
    resource_id: int,
    expected_version: int,
    not_found_detail: str,
    forbidden_detail: str,
    invalid_transition_message: str,
    requested_command: str | None = None,
) -> HTTPException:
    if result.outcome == VersionedUpdateOutcome.NOT_FOUND:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)
    if result.outcome == VersionedUpdateOutcome.UNAUTHORIZED:
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=forbidden_detail)
    if result.outcome == VersionedUpdateOutcome.STALE and result.current_version is not None:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=stale_version_detail(
                resource_type=resource_type,
                resource_id=resource_id,
                expected_version=expected_version,
                current_version=result.current_version,
            ),
        )
    if result.outcome == VersionedUpdateOutcome.INVALID_TRANSITION:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=invalid_state_transition_detail(
                resource_type=resource_type,
                resource_id=resource_id,
                message=invalid_transition_message,
                current_status=result.current_status,
                requested_command=requested_command,
            ),
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=stale_version_detail(
            resource_type=resource_type,
            resource_id=resource_id,
            expected_version=expected_version,
            current_version=result.current_version or expected_version,
        ),
    )


def _record_outcome(
    *,
    resource_type: str,
    operation: str,
    outcome: VersionedUpdateOutcome,
) -> None:
    if outcome == VersionedUpdateOutcome.UNAUTHORIZED:
        return
    OPTIMISTIC_CONCURRENCY_TOTAL.labels(
        resource_type=resource_type,
        operation=operation,
        outcome=outcome.value,
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


def _classify_job_failure(
    db: Session,
    *,
    job_id: int,
    owner_user_id: int,
    expected_version: int,
    operation: str,
) -> VersionedUpdateResult:
    row = (
        db.execute(
            select(
                models.JobPosting.version,
                models.Company.owner_user_id,
            )
            .join(models.Company, models.JobPosting.company_id == models.Company.id)
            .where(models.JobPosting.id == job_id)
        )
        .mappings()
        .first()
    )
    if row is None:
        outcome = VersionedUpdateOutcome.NOT_FOUND
        _record_outcome(resource_type="job", operation=operation, outcome=outcome)
        return VersionedUpdateResult(outcome=outcome)
    if row["owner_user_id"] != owner_user_id:
        return VersionedUpdateResult(outcome=VersionedUpdateOutcome.UNAUTHORIZED)

    outcome = VersionedUpdateOutcome.STALE
    _record_outcome(resource_type="job", operation=operation, outcome=outcome)
    return VersionedUpdateResult(outcome=outcome, current_version=row["version"])


def update_job_with_version(
    db: Session,
    *,
    job_id: int,
    owner_user_id: int,
    expected_version: int,
    updates: dict[str, Any],
    operation: str,
) -> VersionedUpdateResult:
    authorized_company_ids = select(models.Company.id).where(
        models.Company.owner_user_id == owner_user_id
    )
    values = {
        **updates,
        "version": models.JobPosting.version + 1,
        "updated_at": func.now(),
    }
    row = (
        db.execute(
            update(models.JobPosting)
            .where(
                models.JobPosting.id == job_id,
                models.JobPosting.company_id.in_(authorized_company_ids),
                models.JobPosting.version == expected_version,
            )
            .values(**values)
            .returning(models.JobPosting.id, models.JobPosting.version)
        )
        .mappings()
        .first()
    )
    if row is None:
        return _classify_job_failure(
            db,
            job_id=job_id,
            owner_user_id=owner_user_id,
            expected_version=expected_version,
            operation=operation,
        )

    job = _load_job(db, job_id)
    if job is None:
        outcome = VersionedUpdateOutcome.NOT_FOUND
        _record_outcome(resource_type="job", operation=operation, outcome=outcome)
        return VersionedUpdateResult(outcome=outcome)

    outcome = VersionedUpdateOutcome.SUCCESS
    _record_outcome(resource_type="job", operation=operation, outcome=outcome)
    return VersionedUpdateResult(
        outcome=outcome,
        resource=job,
        current_version=row["version"],
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


def _classify_application_failure(
    db: Session,
    *,
    application_id: int,
    actor_user_id: int,
    actor_kind: ActorKind,
    expected_version: int,
    operation: str,
    invalid_current_statuses: set[str],
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
        outcome = VersionedUpdateOutcome.NOT_FOUND
        _record_outcome(resource_type="application", operation=operation, outcome=outcome)
        return VersionedUpdateResult(outcome=outcome)

    if actor_kind == "candidate" and row["candidate_user_id"] != actor_user_id:
        return VersionedUpdateResult(outcome=VersionedUpdateOutcome.UNAUTHORIZED)
    if actor_kind == "hr" and row["owner_user_id"] != actor_user_id:
        return VersionedUpdateResult(outcome=VersionedUpdateOutcome.UNAUTHORIZED)

    if row["version"] != expected_version:
        outcome = VersionedUpdateOutcome.STALE
        _record_outcome(resource_type="application", operation=operation, outcome=outcome)
        return VersionedUpdateResult(outcome=outcome, current_version=row["version"])

    if row["status"] in invalid_current_statuses:
        outcome = VersionedUpdateOutcome.INVALID_TRANSITION
        _record_outcome(resource_type="application", operation=operation, outcome=outcome)
        return VersionedUpdateResult(
            outcome=outcome,
            current_version=row["version"],
            current_status=row["status"],
        )

    outcome = VersionedUpdateOutcome.STALE
    _record_outcome(resource_type="application", operation=operation, outcome=outcome)
    return VersionedUpdateResult(outcome=outcome, current_version=row["version"])


def update_application_status_with_version(
    db: Session,
    *,
    application_id: int,
    actor_user_id: int,
    actor_kind: ActorKind,
    expected_version: int,
    new_status: str,
    note: str | None,
    operation: str,
    invalid_current_statuses: set[str] | None = None,
    include_candidate: bool = False,
) -> VersionedUpdateResult:
    invalid_statuses = invalid_current_statuses or set()
    conditions = _application_authorization_conditions(
        application_id=application_id,
        actor_user_id=actor_user_id,
        actor_kind=actor_kind,
    )
    conditions.append(models.JobApplication.version == expected_version)
    if invalid_statuses:
        conditions.append(~models.JobApplication.status.in_(invalid_statuses))

    db.execute(
        insert(models.ApplicationStatusHistory).from_select(
            [
                "job_application_id",
                "old_status",
                "new_status",
                "changed_by_user_id",
                "note",
            ],
            select(
                models.JobApplication.id,
                models.JobApplication.status,
                literal(new_status),
                literal(actor_user_id),
                literal(note),
            ).where(*conditions),
        )
    )
    row = (
        db.execute(
            update(models.JobApplication)
            .where(*conditions)
            .values(
                status=new_status,
                version=models.JobApplication.version + 1,
                updated_at=func.now(),
            )
            .returning(models.JobApplication.id, models.JobApplication.version)
        )
        .mappings()
        .first()
    )
    if row is None:
        db.rollback()
        return _classify_application_failure(
            db,
            application_id=application_id,
            actor_user_id=actor_user_id,
            actor_kind=actor_kind,
            expected_version=expected_version,
            operation=operation,
            invalid_current_statuses=invalid_statuses,
        )

    application = _load_application(
        db,
        application_id,
        include_candidate=include_candidate,
    )
    if application is None:
        db.rollback()
        outcome = VersionedUpdateOutcome.NOT_FOUND
        _record_outcome(resource_type="application", operation=operation, outcome=outcome)
        return VersionedUpdateResult(outcome=outcome)

    outcome = VersionedUpdateOutcome.SUCCESS
    _record_outcome(resource_type="application", operation=operation, outcome=outcome)
    return VersionedUpdateResult(
        outcome=outcome,
        resource=application,
        current_version=row["version"],
    )
