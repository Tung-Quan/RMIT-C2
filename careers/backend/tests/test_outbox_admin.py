from datetime import timedelta

import pytest

from app.db import models
from app.db.database import SessionLocal
from app.services.outbox import (
    OUTBOX_STATUS_DEAD,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PUBLISHED,
    enqueue_event,
    utc_now,
)
from app.workers import outbox_admin


def test_outbox_admin_list_dead_outputs_bounded_rows(capsys):
    db = SessionLocal()
    try:
        event = enqueue_event(
            db,
            event_type="job.closed.v1",
            aggregate_type="job",
            aggregate_id=7,
            aggregate_version=3,
            command_name="close",
            data={"fromStatus": "published", "toStatus": "closed", "companyId": "1"},
        )
        event.status = OUTBOX_STATUS_DEAD
        event.attempts = 2
        event.last_error = "transport failed"
        db.commit()
        event_id = event.id
    finally:
        db.close()

    assert outbox_admin.main(["list-dead", "--limit", "10"]) == 0

    output = capsys.readouterr().out
    assert f"event_id={event_id}" in output
    assert "event_type=job.closed.v1" in output
    assert "last_error=transport failed" in output


def test_outbox_admin_requeue_validates_uuid_and_requeues_one_dead_event(capsys):
    with pytest.raises(SystemExit) as invalid:
        outbox_admin.main(["requeue", "--event-id", "not-a-uuid"])
    assert invalid.value.code == 2

    db = SessionLocal()
    try:
        event = enqueue_event(
            db,
            event_type="application.rejected.v1",
            aggregate_type="job_application",
            aggregate_id=9,
            aggregate_version=2,
            command_name="reject",
            data={
                "fromStatus": "submitted",
                "toStatus": "rejected",
                "jobId": "7",
                "candidateUserId": "3",
            },
        )
        event.status = OUTBOX_STATUS_DEAD
        event.attempts = 2
        event.last_error = "invalid event"
        db.commit()
        event_id = event.id
    finally:
        db.close()

    assert outbox_admin.main(["requeue", "--event-id", event_id]) == 0

    output = capsys.readouterr().out
    assert f"event_id={event_id} requeued=1" in output
    db = SessionLocal()
    try:
        row = db.get(models.OutboxEvent, event_id)
        assert row is not None
        assert row.status == OUTBOX_STATUS_PENDING
        assert row.attempts == 0
        assert row.last_error is None
    finally:
        db.close()


def test_outbox_admin_cleanup_published_deletes_only_old_rows(capsys):
    db = SessionLocal()
    try:
        old_event = enqueue_event(
            db,
            event_type="job.published.v1",
            aggregate_type="job",
            aggregate_id=7,
            aggregate_version=1,
            command_name="publish",
            data={"fromStatus": "draft", "toStatus": "published", "companyId": "1"},
        )
        old_event.status = OUTBOX_STATUS_PUBLISHED
        old_event.published_at = utc_now() - timedelta(days=31)

        recent_event = enqueue_event(
            db,
            event_type="job.closed.v1",
            aggregate_type="job",
            aggregate_id=7,
            aggregate_version=2,
            command_name="close",
            data={"fromStatus": "published", "toStatus": "closed", "companyId": "1"},
        )
        recent_event.status = OUTBOX_STATUS_PUBLISHED
        recent_event.published_at = utc_now()
        db.commit()
        old_event_id = old_event.id
        recent_event_id = recent_event.id
    finally:
        db.close()

    assert (
        outbox_admin.main(["cleanup-published", "--older-than-days", "30", "--batch-size", "50"])
        == 0
    )

    output = capsys.readouterr().out
    assert "deleted=1 older_than_days=30" in output
    db = SessionLocal()
    try:
        assert db.get(models.OutboxEvent, old_event_id) is None
        assert db.get(models.OutboxEvent, recent_event_id) is not None
    finally:
        db.close()
