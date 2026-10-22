from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.db import models
from app.db.database import SessionLocal
from app.services.idempotency_service import (
    cleanup_expired_terminal_idempotency_records,
    replay_or_conflict_response,
    utc_now,
)


def add_record(*, key: str, status: str, expires_delta: timedelta) -> None:
    db = SessionLocal()
    try:
        db.add(
            models.IdempotencyRecord(
                scope="user:1:candidate_apply",
                idempotency_key=key,
                request_hash="a" * 64,
                status=status,
                response_status=201 if status == "completed" else None,
                response_body={"ok": True} if status == "completed" else None,
                expires_at=utc_now() + expires_delta,
            )
        )
        db.commit()
    finally:
        db.close()


def count_records() -> int:
    db = SessionLocal()
    try:
        return db.query(models.IdempotencyRecord).count()
    finally:
        db.close()


def test_cleanup_deletes_only_expired_terminal_idempotency_records():
    add_record(key="expired-completed", status="completed", expires_delta=timedelta(days=-1))
    add_record(key="expired-failed", status="failed", expires_delta=timedelta(days=-1))
    add_record(key="expired-processing", status="processing", expires_delta=timedelta(days=-1))
    add_record(key="fresh-completed", status="completed", expires_delta=timedelta(days=1))

    db = SessionLocal()
    try:
        deleted = cleanup_expired_terminal_idempotency_records(db)
        db.commit()
    finally:
        db.close()

    assert deleted == 2
    assert count_records() == 2


def test_expired_processing_record_returns_expired_conflict():
    record = models.IdempotencyRecord(
        scope="user:1:candidate_apply",
        idempotency_key="expired-processing",
        request_hash="b" * 64,
        status="processing",
        expires_at=utc_now() - timedelta(seconds=1),
    )

    with pytest.raises(HTTPException) as exc_info:
        replay_or_conflict_response(
            record,
            request_hash="b" * 64,
            operation="candidate_apply",
        )

    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert exc_info.value.status_code == 409
    assert detail["code"] == "idempotency_request_expired"
