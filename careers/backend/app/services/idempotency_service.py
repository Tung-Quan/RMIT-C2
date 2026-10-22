import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.metrics import (
    IDEMPOTENCY_MISMATCH_TOTAL,
    IDEMPOTENCY_REPLAY_TOTAL,
    IDEMPOTENCY_RESERVATION_TOTAL,
)
from app.db import models

IDEMPOTENCY_RETENTION_DAYS = 7
IDEMPOTENCY_STATUS_COMPLETED = "completed"
IDEMPOTENCY_STATUS_FAILED = "failed"
IDEMPOTENCY_STATUS_PROCESSING = "processing"
IDEMPOTENCY_TERMINAL_STATUSES = (IDEMPOTENCY_STATUS_COMPLETED, IDEMPOTENCY_STATUS_FAILED)


def utc_now() -> datetime:
    return datetime.now(UTC)


def normalize_idempotency_key(idempotency_key: str) -> str:
    normalized = idempotency_key.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "idempotency_key_required",
                "message": "Idempotency-Key must not be blank.",
            },
        )
    if len(normalized) > 255:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "idempotency_key_too_long",
                "message": "Idempotency-Key must be 255 characters or fewer.",
            },
        )
    return normalized


def deterministic_request_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        jsonable_encoder(payload),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def idempotency_scope(*, actor_id: int, operation: str) -> str:
    return f"user:{actor_id}:{operation}"


def reserve_idempotency_record(
    db: Session,
    *,
    scope: str,
    idempotency_key: str,
    request_hash: str,
    operation: str,
) -> models.IdempotencyRecord | JSONResponse:
    record = models.IdempotencyRecord(
        scope=scope,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status=IDEMPOTENCY_STATUS_PROCESSING,
        expires_at=utc_now() + timedelta(days=IDEMPOTENCY_RETENTION_DAYS),
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = get_idempotency_record(db, scope=scope, idempotency_key=idempotency_key)
        if existing:
            IDEMPOTENCY_RESERVATION_TOTAL.labels(operation=operation, result="existing").inc()
            return replay_or_conflict_response(
                existing,
                request_hash=request_hash,
                operation=operation,
            )
        raise

    IDEMPOTENCY_RESERVATION_TOTAL.labels(operation=operation, result="reserved").inc()
    return record


def get_idempotency_record(
    db: Session,
    *,
    scope: str,
    idempotency_key: str,
) -> models.IdempotencyRecord | None:
    return (
        db.query(models.IdempotencyRecord)
        .filter(
            models.IdempotencyRecord.scope == scope,
            models.IdempotencyRecord.idempotency_key == idempotency_key,
        )
        .first()
    )


def replay_or_conflict_response(
    record: models.IdempotencyRecord,
    *,
    request_hash: str,
    operation: str,
) -> JSONResponse:
    if record.request_hash != request_hash:
        IDEMPOTENCY_MISMATCH_TOTAL.labels(operation=operation).inc()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "idempotency_key_reused",
                "message": "Idempotency-Key was already used with a different request payload.",
            },
        )

    if record.status == IDEMPOTENCY_STATUS_PROCESSING and record.expires_at <= utc_now():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "idempotency_request_expired",
                "message": (
                    "A previous request with this Idempotency-Key expired before completion."
                ),
            },
        )

    if record.status != IDEMPOTENCY_STATUS_COMPLETED or record.response_status is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "idempotency_request_in_progress",
                "message": "A request with this Idempotency-Key is still being processed.",
            },
        )

    IDEMPOTENCY_REPLAY_TOTAL.labels(operation=operation).inc()
    return JSONResponse(
        status_code=record.response_status,
        content=record.response_body or {},
        headers={"Idempotency-Replayed": "true"},
    )


def complete_idempotency_record(
    record: models.IdempotencyRecord,
    *,
    response_status: int,
    response_body: Any,
    resource_type: str | None = None,
    resource_id: int | None = None,
) -> dict[str, Any]:
    body = cast(dict[str, Any], jsonable_encoder(response_body))
    record.status = IDEMPOTENCY_STATUS_COMPLETED
    record.response_status = response_status
    record.response_body = body
    record.resource_type = resource_type
    record.resource_id = resource_id
    record.completed_at = utc_now()
    return body


def error_response_body(exc: HTTPException) -> dict[str, Any]:
    body: dict[str, Any] = {"detail": jsonable_encoder(exc.detail)}
    return body


def cleanup_expired_terminal_idempotency_records(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    cutoff = now or utc_now()
    result = db.execute(
        delete(models.IdempotencyRecord).where(
            models.IdempotencyRecord.status.in_(IDEMPOTENCY_TERMINAL_STATUSES),
            models.IdempotencyRecord.expires_at <= cutoff,
        )
    )
    return result.rowcount or 0
