import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.core.metrics import (
    OUTBOX_DEAD_EVENTS,
    OUTBOX_DEAD_TOTAL,
    OUTBOX_EVENTS_CLAIMED_TOTAL,
    OUTBOX_EVENTS_ENQUEUED_TOTAL,
    OUTBOX_LEASE_RECLAIMED_TOTAL,
    OUTBOX_OLDEST_PENDING_AGE_SECONDS,
    OUTBOX_PENDING_EVENTS,
    OUTBOX_PUBLISH_TOTAL,
    OUTBOX_RETRY_TOTAL,
    OUTBOX_TRANSPORT_ERROR_TOTAL,
)
from app.db import models

OUTBOX_STATUS_PENDING = "PENDING"
OUTBOX_STATUS_PROCESSING = "PROCESSING"
OUTBOX_STATUS_PUBLISHED = "PUBLISHED"
OUTBOX_STATUS_DEAD = "DEAD"
OUTBOX_STATUSES = (
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PROCESSING,
    OUTBOX_STATUS_PUBLISHED,
    OUTBOX_STATUS_DEAD,
)
OUTBOX_SCHEMA_VERSION = 1
OUTBOX_ERROR_MAX_LENGTH = 512
OUTBOX_EVENT_FAMILIES = ("application", "job")

EventFamily = Literal["application", "job"]

JOB_COMMAND_EVENT_TYPES = {
    "publish": "job.published.v1",
    "close": "job.closed.v1",
    "reopen": "job.reopened.v1",
    "archive": "job.archived.v1",
    "delete_draft": "job.draft_deleted.v1",
}

APPLICATION_COMMAND_EVENT_TYPES = {
    "advance": "application.advanced.v1",
    "reject": "application.rejected.v1",
    "withdraw": "application.withdrawn.v1",
}


@dataclass(frozen=True)
class ClaimedOutboxEvent:
    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    command_name: str
    payload: dict[str, Any]
    attempts: int

    @property
    def event_family(self) -> EventFamily:
        return event_family_from_aggregate_type(self.aggregate_type)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _isoformat_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def event_family_from_aggregate_type(aggregate_type: str) -> EventFamily:
    if aggregate_type == "job":
        return "job"
    return "application"


def derive_deduplication_key(
    *,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    event_type: str,
) -> str:
    return f"{aggregate_type}:{aggregate_id}:{aggregate_version}:{event_type}"


def build_event_envelope(
    *,
    event_id: str,
    event_type: str,
    schema_version: int,
    occurred_at: datetime,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    command_name: str,
    causation_id: str,
    correlation_id: str | None,
    data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "eventId": event_id,
        "eventType": event_type,
        "schemaVersion": schema_version,
        "occurredAt": _isoformat_z(occurred_at),
        "aggregate": {
            "type": aggregate_type,
            "id": aggregate_id,
            "version": aggregate_version,
        },
        "command": {
            "name": command_name,
            "causationId": causation_id,
        },
        "correlationId": correlation_id,
        "data": jsonable_encoder(data),
    }


def enqueue_event(
    db: Session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: int | str,
    aggregate_version: int,
    command_name: str,
    data: dict[str, Any],
    causation_id: str | None = None,
    correlation_id: str | None = None,
    event_id: str | None = None,
    occurred_at: datetime | None = None,
) -> models.OutboxEvent:
    event_id = event_id or str(uuid.uuid4())
    causation_id = causation_id or str(uuid.uuid4())
    occurred_at = occurred_at or utc_now()
    aggregate_id_value = str(aggregate_id)
    deduplication_key = derive_deduplication_key(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id_value,
        aggregate_version=aggregate_version,
        event_type=event_type,
    )
    existing = (
        db.query(models.OutboxEvent)
        .filter(models.OutboxEvent.deduplication_key == deduplication_key)
        .first()
    )
    if existing is not None:
        return existing

    payload = build_event_envelope(
        event_id=event_id,
        event_type=event_type,
        schema_version=OUTBOX_SCHEMA_VERSION,
        occurred_at=occurred_at,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id_value,
        aggregate_version=aggregate_version,
        command_name=command_name,
        causation_id=causation_id,
        correlation_id=correlation_id,
        data=data,
    )
    event = models.OutboxEvent(
        id=event_id,
        event_type=event_type,
        schema_version=OUTBOX_SCHEMA_VERSION,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id_value,
        aggregate_version=aggregate_version,
        command_name=command_name,
        causation_id=causation_id,
        correlation_id=correlation_id,
        deduplication_key=deduplication_key,
        payload=payload,
        status=OUTBOX_STATUS_PENDING,
        attempts=0,
        available_at=occurred_at,
        occurred_at=occurred_at,
    )
    db.add(event)
    db.flush()
    OUTBOX_EVENTS_ENQUEUED_TOTAL.labels(
        event_family=event_family_from_aggregate_type(aggregate_type)
    ).inc()
    return event


def enqueue_application_submitted_event(
    db: Session,
    *,
    application_id: int,
    application_version: int,
    job_id: int,
    candidate_user_id: int,
    attached_document_ids: list[int],
) -> models.OutboxEvent:
    return enqueue_event(
        db,
        event_type="application.submitted.v1",
        aggregate_type="job_application",
        aggregate_id=application_id,
        aggregate_version=application_version,
        command_name="submit",
        data={
            "status": "submitted",
            "jobId": str(job_id),
            "candidateUserId": str(candidate_user_id),
            "attachedDocumentIds": [str(document_id) for document_id in attached_document_ids],
        },
    )


def enqueue_job_workflow_event(
    db: Session,
    *,
    command_name: str,
    job_id: int,
    aggregate_version: int,
    from_status: str,
    to_status: str,
    company_id: int,
) -> models.OutboxEvent:
    return enqueue_event(
        db,
        event_type=JOB_COMMAND_EVENT_TYPES[command_name],
        aggregate_type="job",
        aggregate_id=job_id,
        aggregate_version=aggregate_version,
        command_name=command_name,
        data={
            "fromStatus": from_status,
            "toStatus": to_status,
            "companyId": str(company_id),
        },
    )


def enqueue_application_workflow_event(
    db: Session,
    *,
    command_name: str,
    application_id: int,
    aggregate_version: int,
    from_status: str,
    to_status: str,
    job_id: int,
    candidate_user_id: int,
) -> models.OutboxEvent:
    return enqueue_event(
        db,
        event_type=APPLICATION_COMMAND_EVENT_TYPES[command_name],
        aggregate_type="job_application",
        aggregate_id=application_id,
        aggregate_version=aggregate_version,
        command_name=command_name,
        data={
            "fromStatus": from_status,
            "toStatus": to_status,
            "jobId": str(job_id),
            "candidateUserId": str(candidate_user_id),
        },
    )


def _claimable_events_query(now: datetime):
    event = models.OutboxEvent
    earlier = aliased(models.OutboxEvent)
    earlier_unpublished_exists = (
        select(earlier.id)
        .where(
            earlier.aggregate_type == event.aggregate_type,
            earlier.aggregate_id == event.aggregate_id,
            earlier.aggregate_version < event.aggregate_version,
            earlier.status != OUTBOX_STATUS_PUBLISHED,
        )
        .exists()
    )
    return (
        select(event.id, event.status)
        .where(
            or_(
                and_(
                    event.status == OUTBOX_STATUS_PENDING,
                    event.available_at <= now,
                ),
                and_(
                    event.status == OUTBOX_STATUS_PROCESSING,
                    event.locked_until <= now,
                ),
            ),
            ~earlier_unpublished_exists,
        )
        .order_by(event.available_at.asc(), event.occurred_at.asc(), event.id.asc())
    )


def claim_outbox_events(
    db: Session,
    *,
    worker_id: str,
    batch_size: int,
    lease_seconds: int,
    now: datetime | None = None,
) -> list[ClaimedOutboxEvent]:
    if batch_size <= 0:
        return []
    claim_time = now or utc_now()
    claim_query = _claimable_events_query(claim_time).limit(batch_size)
    if db.get_bind().dialect.name == "postgresql":
        claim_query = claim_query.with_for_update(skip_locked=True)

    rows = db.execute(claim_query).mappings().all()
    if not rows:
        return []

    event_ids = [str(row["id"]) for row in rows]
    previous_status_by_id = {str(row["id"]): str(row["status"]) for row in rows}
    locked_until = claim_time + timedelta(seconds=lease_seconds)
    db.execute(
        update(models.OutboxEvent)
        .where(models.OutboxEvent.id.in_(event_ids))
        .values(
            status=OUTBOX_STATUS_PROCESSING,
            locked_at=claim_time,
            locked_until=locked_until,
            locked_by=worker_id,
        )
    )
    events = (
        db.execute(select(models.OutboxEvent).where(models.OutboxEvent.id.in_(event_ids)))
        .scalars()
        .all()
    )
    events_by_id = {event.id: event for event in events}
    claimed: list[ClaimedOutboxEvent] = []
    for event_id in event_ids:
        event = events_by_id[event_id]
        family = event_family_from_aggregate_type(event.aggregate_type)
        OUTBOX_EVENTS_CLAIMED_TOTAL.labels(event_family=family).inc()
        if previous_status_by_id[event_id] == OUTBOX_STATUS_PROCESSING:
            OUTBOX_LEASE_RECLAIMED_TOTAL.labels(event_family=family).inc()
        claimed.append(
            ClaimedOutboxEvent(
                event_id=event.id,
                event_type=event.event_type,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                aggregate_version=event.aggregate_version,
                command_name=event.command_name,
                payload=event.payload,
                attempts=event.attempts,
            )
        )
    return claimed


def mark_event_published(
    db: Session,
    *,
    event_id: str,
    publisher: str,
    published_at: datetime | None = None,
) -> bool:
    event = db.get(models.OutboxEvent, event_id)
    if event is None:
        return False
    event.status = OUTBOX_STATUS_PUBLISHED
    event.published_at = published_at or utc_now()
    event.locked_at = None
    event.locked_until = None
    event.locked_by = None
    event.last_error = None
    OUTBOX_PUBLISH_TOTAL.labels(
        event_family=event_family_from_aggregate_type(event.aggregate_type),
        outcome="success",
        publisher=publisher,
    ).inc()
    return True


def _bounded_error(error: BaseException | str) -> str:
    message = str(error)
    if len(message) <= OUTBOX_ERROR_MAX_LENGTH:
        return message
    return message[: OUTBOX_ERROR_MAX_LENGTH - 3] + "..."


def compute_retry_delay(
    *,
    attempts: int,
    base_delay_seconds: int,
    max_delay_seconds: int,
) -> timedelta:
    raw_delay = min(max_delay_seconds, base_delay_seconds * (2 ** max(attempts - 1, 0)))
    jitter = random.uniform(0, min(raw_delay * 0.1, 30))
    return timedelta(seconds=min(max_delay_seconds, raw_delay + jitter))


def mark_event_retry_or_dead(
    db: Session,
    *,
    event_id: str,
    publisher: str,
    error: BaseException | str,
    error_category: str = "unknown_transport_error",
    retryable: bool = True,
    max_attempts: int,
    base_delay_seconds: int,
    max_delay_seconds: int,
    now: datetime | None = None,
) -> Literal["retry", "dead", "missing"]:
    event = db.get(models.OutboxEvent, event_id)
    if event is None:
        return "missing"
    failure_time = now or utc_now()
    event.attempts += 1
    event.last_error = _bounded_error(error)
    event.locked_at = None
    event.locked_until = None
    event.locked_by = None
    family = event_family_from_aggregate_type(event.aggregate_type)
    OUTBOX_TRANSPORT_ERROR_TOTAL.labels(
        event_family=family,
        publisher=publisher,
        error_category=error_category,
        retryable=str(retryable).lower(),
    ).inc()
    if not retryable or event.attempts >= max_attempts:
        event.status = OUTBOX_STATUS_DEAD
        event.available_at = failure_time
        OUTBOX_DEAD_TOTAL.labels(event_family=family, publisher=publisher).inc()
        OUTBOX_PUBLISH_TOTAL.labels(
            event_family=family,
            outcome="dead",
            publisher=publisher,
        ).inc()
        return "dead"

    event.status = OUTBOX_STATUS_PENDING
    event.available_at = failure_time + compute_retry_delay(
        attempts=event.attempts,
        base_delay_seconds=base_delay_seconds,
        max_delay_seconds=max_delay_seconds,
    )
    OUTBOX_RETRY_TOTAL.labels(event_family=family, publisher=publisher).inc()
    OUTBOX_PUBLISH_TOTAL.labels(
        event_family=family,
        outcome="retry",
        publisher=publisher,
    ).inc()
    return "retry"


def requeue_dead_event(
    db: Session,
    *,
    event_id: str,
    now: datetime | None = None,
) -> bool:
    event = db.get(models.OutboxEvent, event_id)
    if event is None or event.status != OUTBOX_STATUS_DEAD:
        return False
    event.status = OUTBOX_STATUS_PENDING
    event.attempts = 0
    event.available_at = now or utc_now()
    event.locked_at = None
    event.locked_until = None
    event.locked_by = None
    event.last_error = None
    return True


def requeue_dead_events(
    db: Session,
    *,
    event_family: EventFamily | None = None,
    limit: int = 100,
    now: datetime | None = None,
) -> int:
    query = (
        db.query(models.OutboxEvent)
        .filter(models.OutboxEvent.status == OUTBOX_STATUS_DEAD)
        .order_by(models.OutboxEvent.created_at.asc(), models.OutboxEvent.id.asc())
        .limit(limit)
    )
    if event_family == "job":
        query = query.filter(models.OutboxEvent.aggregate_type == "job")
    elif event_family == "application":
        query = query.filter(models.OutboxEvent.aggregate_type == "job_application")

    count = 0
    for event in query.all():
        if requeue_dead_event(db, event_id=event.id, now=now):
            count += 1
    return count


def dead_event_counts(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            select(models.OutboxEvent.event_type, func.count(models.OutboxEvent.id))
            .where(models.OutboxEvent.status == OUTBOX_STATUS_DEAD)
            .group_by(models.OutboxEvent.event_type)
            .order_by(models.OutboxEvent.event_type.asc())
        )
        .tuples()
        .all()
    )
    return [{"eventType": event_type, "count": count} for event_type, count in rows]


def cleanup_published_events(
    db: Session,
    *,
    older_than: datetime,
    batch_size: int,
) -> int:
    ids = [
        row[0]
        for row in db.execute(
            select(models.OutboxEvent.id)
            .where(
                models.OutboxEvent.status == OUTBOX_STATUS_PUBLISHED,
                models.OutboxEvent.published_at < older_than,
            )
            .order_by(models.OutboxEvent.published_at.asc(), models.OutboxEvent.id.asc())
            .limit(batch_size)
        ).all()
    ]
    if not ids:
        return 0
    result = db.execute(delete(models.OutboxEvent).where(models.OutboxEvent.id.in_(ids)))
    return result.rowcount or 0


def refresh_outbox_gauges(db: Session, *, now: datetime | None = None) -> None:
    snapshot_time = now or utc_now()
    for family in OUTBOX_EVENT_FAMILIES:
        OUTBOX_PENDING_EVENTS.labels(event_family=family).set(0)
        OUTBOX_DEAD_EVENTS.labels(event_family=family).set(0)
        OUTBOX_OLDEST_PENDING_AGE_SECONDS.labels(event_family=family).set(0)

    count_rows = (
        db.execute(
            select(
                models.OutboxEvent.aggregate_type,
                models.OutboxEvent.status,
                func.count(models.OutboxEvent.id),
            )
            .where(models.OutboxEvent.status.in_([OUTBOX_STATUS_PENDING, OUTBOX_STATUS_DEAD]))
            .group_by(models.OutboxEvent.aggregate_type, models.OutboxEvent.status)
        )
        .tuples()
        .all()
    )
    for aggregate_type, event_status, count in count_rows:
        family = event_family_from_aggregate_type(aggregate_type)
        if event_status == OUTBOX_STATUS_PENDING:
            OUTBOX_PENDING_EVENTS.labels(event_family=family).set(count)
        elif event_status == OUTBOX_STATUS_DEAD:
            OUTBOX_DEAD_EVENTS.labels(event_family=family).set(count)

    oldest_rows = (
        db.execute(
            select(
                models.OutboxEvent.aggregate_type,
                func.min(models.OutboxEvent.available_at),
            )
            .where(models.OutboxEvent.status == OUTBOX_STATUS_PENDING)
            .group_by(models.OutboxEvent.aggregate_type)
        )
        .tuples()
        .all()
    )
    for aggregate_type, oldest_available_at in oldest_rows:
        if oldest_available_at is None:
            continue
        if oldest_available_at.tzinfo is None:
            oldest_available_at = oldest_available_at.replace(tzinfo=UTC)
        age = max(0.0, (snapshot_time - oldest_available_at).total_seconds())
        OUTBOX_OLDEST_PENDING_AGE_SECONDS.labels(
            event_family=event_family_from_aggregate_type(aggregate_type)
        ).set(age)
