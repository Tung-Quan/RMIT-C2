import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db import models
from app.db.database import SessionLocal
from app.main import app
from app.services.outbox import (
    OUTBOX_STATUS_DEAD,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PUBLISHED,
    cleanup_published_events,
    enqueue_event,
    requeue_dead_event,
    utc_now,
)
from app.services.outbox_publishers import RecordingOutboxPublisher
from app.workers.outbox_dispatcher import run_once


def register_and_login(client, *, email, role="candidate", full_name="Test User"):
    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": full_name,
            "password": "Strong!Pass123",
            "role": role,
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={"email": email, "password": "Strong!Pass123"},
    )
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def create_company(client, headers, *, name="Outbox Labs"):
    response = client.post(
        "/companies",
        json={
            "name": name,
            "description": "Tests transactional outbox events.",
            "website": None,
            "industry": "Technology",
            "location": "Singapore",
            "logo_url": None,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_job(client, headers, *, status="draft", title="Outbox Backend Intern"):
    response = client.post(
        "/hr/jobs",
        json={
            "title": title,
            "description": "Work on reliable event delivery.",
            "requirements": "Python and SQL",
            "responsibilities": "Build APIs",
            "location": "Remote",
            "employment_type": "early_career",
            "work_mode": "remote",
            "salary_min": 0,
            "salary_max": 1000,
            "deadline": "2026-12-31",
            "status": status,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_tracker_application(client, headers):
    response = client.post(
        "/applications",
        json={
            "company_name": "Tracker Co",
            "position_title": "Saved Role",
            "job_description": "Reusable document holder.",
            "application_status": "Saved",
            "deadline": None,
            "notes": None,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def upload_document(client, headers, application_id):
    response = client.post(
        f"/applications/{application_id}/documents",
        data={"document_type": "CV"},
        files={"file": ("cv.txt", b"FastAPI outbox events", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def setup_job_application_flow(client, *, email_prefix="outbox"):
    hr_headers = register_and_login(
        client,
        email=f"{email_prefix}-hr@example.edu",
        role="hr",
        full_name="Outbox HR",
    )
    create_company(client, hr_headers, name=f"{email_prefix} Company")
    job = create_job(client, hr_headers, status="published")

    candidate_headers = register_and_login(
        client,
        email=f"{email_prefix}-candidate@example.edu",
        full_name="Outbox Candidate",
    )
    tracker = create_tracker_application(client, candidate_headers)
    document = upload_document(client, candidate_headers, tracker["id"])
    apply_response = client.post(
        f"/jobs/{job['id']}/apply",
        json={
            "cover_letter_text": "Please consider me.",
            "candidate_note": "Available immediately.",
            "document_ids": [document["id"]],
        },
        headers=candidate_headers,
    )
    assert apply_response.status_code == 201
    return hr_headers, candidate_headers, job, document, apply_response.json()


def outbox_events() -> list[models.OutboxEvent]:
    db = SessionLocal()
    try:
        events = db.query(models.OutboxEvent).order_by(models.OutboxEvent.created_at.asc()).all()
        for event in events:
            db.expunge(event)
        return events
    finally:
        db.close()


def count_rows(model: type[object]) -> int:
    db = SessionLocal()
    try:
        return db.query(model).count()
    finally:
        db.close()


def test_candidate_apply_emits_submitted_event_and_idempotent_replay_does_not_duplicate(client):
    _hr_headers, candidate_headers, job, document, application = setup_job_application_flow(
        client,
        email_prefix="outbox-apply",
    )
    first_events = outbox_events()
    assert [event.event_type for event in first_events] == ["application.submitted.v1"]
    event = first_events[0]
    assert event.aggregate_type == "job_application"
    assert event.aggregate_id == str(application["id"])
    assert event.aggregate_version == 1
    assert event.payload["aggregate"]["version"] == 1
    assert event.payload["data"] == {
        "status": "submitted",
        "jobId": str(job["id"]),
        "candidateUserId": str(application["candidate_user_id"]),
        "attachedDocumentIds": [str(document["id"])],
    }
    assert "cover_letter_text" not in str(event.payload)
    assert "candidate_note" not in str(event.payload)
    assert "email" not in str(event.payload).lower()

    replay_response = client.post(
        f"/jobs/{job['id']}/apply",
        json={
            "cover_letter_text": "Please consider me.",
            "candidate_note": "Available immediately.",
            "document_ids": [document["id"]],
        },
        headers={**candidate_headers, "Idempotency-Key": "apply-outbox-key"},
    )
    assert replay_response.status_code == 409
    assert len(outbox_events()) == 1


def test_idempotent_candidate_apply_exact_replay_and_mismatch_create_no_extra_event(client):
    hr_headers = register_and_login(
        client,
        email="outbox-idem-hr@example.edu",
        role="hr",
        full_name="Outbox Idempotent HR",
    )
    create_company(client, hr_headers)
    job = create_job(client, hr_headers, status="published")
    candidate_headers = register_and_login(
        client,
        email="outbox-idem-candidate@example.edu",
        full_name="Outbox Idempotent Candidate",
    )
    tracker = create_tracker_application(client, candidate_headers)
    document = upload_document(client, candidate_headers, tracker["id"])
    payload = {
        "cover_letter_text": "Please consider me.",
        "candidate_note": "Available immediately.",
        "document_ids": [document["id"]],
    }
    first_response = client.post(
        f"/jobs/{job['id']}/apply",
        json=payload,
        headers={**candidate_headers, "Idempotency-Key": "submitted-outbox-key"},
    )
    assert first_response.status_code == 201
    assert len(outbox_events()) == 1

    replay_response = client.post(
        f"/jobs/{job['id']}/apply",
        json=payload,
        headers={**candidate_headers, "Idempotency-Key": "submitted-outbox-key"},
    )
    assert replay_response.status_code == 201
    assert replay_response.headers["Idempotency-Replayed"] == "true"
    assert len(outbox_events()) == 1

    mismatch_response = client.post(
        f"/jobs/{job['id']}/apply",
        json={**payload, "candidate_note": "Changed"},
        headers={**candidate_headers, "Idempotency-Key": "submitted-outbox-key"},
    )
    assert mismatch_response.status_code == 409
    assert mismatch_response.json()["detail"]["code"] == "idempotency_key_reused"
    assert len(outbox_events()) == 1


def test_job_commands_emit_distinct_events_and_delete_event_survives_deleted_job(client):
    hr_headers = register_and_login(
        client,
        email="outbox-job-hr@example.edu",
        role="hr",
        full_name="Outbox Job HR",
    )
    create_company(client, hr_headers)
    job = create_job(client, hr_headers)

    publish_response = client.post(
        f"/hr/jobs/{job['id']}/publish",
        json={"expectedVersion": job["version"]},
        headers={**hr_headers, "Idempotency-Key": "job-publish-outbox"},
    )
    assert publish_response.status_code == 200
    replay_response = client.post(
        f"/hr/jobs/{job['id']}/publish",
        json={"expectedVersion": job["version"]},
        headers={**hr_headers, "Idempotency-Key": "job-publish-outbox"},
    )
    assert replay_response.status_code == 200
    assert replay_response.headers["Idempotency-Replayed"] == "true"

    close_response = client.post(
        f"/hr/jobs/{job['id']}/close",
        json={"expectedVersion": publish_response.json()["version"]},
        headers=hr_headers,
    )
    assert close_response.status_code == 200
    reopen_response = client.post(
        f"/hr/jobs/{job['id']}/reopen",
        json={"expectedVersion": close_response.json()["version"]},
        headers=hr_headers,
    )
    assert reopen_response.status_code == 200
    archive_response = client.post(
        f"/hr/jobs/{job['id']}/archive",
        json={"expectedVersion": reopen_response.json()["version"]},
        headers=hr_headers,
    )
    assert archive_response.status_code == 200

    draft = create_job(client, hr_headers, title="Outbox Disposable Draft")
    delete_response = client.post(
        f"/hr/jobs/{draft['id']}/delete-draft",
        json={"expectedVersion": draft["version"]},
        headers=hr_headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["version"] == draft["version"] + 1
    assert client.get(f"/hr/jobs/{draft['id']}", headers=hr_headers).status_code == 404

    events = outbox_events()
    assert [event.event_type for event in events] == [
        "job.published.v1",
        "job.closed.v1",
        "job.reopened.v1",
        "job.archived.v1",
        "job.draft_deleted.v1",
    ]
    assert events[3].payload["data"]["toStatus"] == "closed"
    assert events[4].aggregate_id == str(draft["id"])
    assert events[4].aggregate_version == draft["version"] + 1


def test_application_command_event_commit_and_failure_rollback(client, monkeypatch):
    hr_headers, _candidate_headers, _job, _document, application = setup_job_application_flow(
        client,
        email_prefix="outbox-application",
    )
    review_response = client.post(
        f"/hr/applications/{application['id']}/advance",
        json={"targetStage": "under_review", "expectedVersion": application["version"]},
        headers=hr_headers,
    )
    assert review_response.status_code == 200
    events = outbox_events()
    assert [event.event_type for event in events] == [
        "application.submitted.v1",
        "application.advanced.v1",
    ]
    assert events[-1].aggregate_version == 2
    assert events[-1].payload["data"]["fromStatus"] == "submitted"
    assert events[-1].payload["data"]["toStatus"] == "under_review"
    assert count_rows(models.ApplicationStatusHistory) == 2

    stale_response = client.post(
        f"/hr/applications/{application['id']}/advance",
        json={"targetStage": "shortlisted", "expectedVersion": application["version"]},
        headers=hr_headers,
    )
    assert stale_response.status_code == 409
    assert len(outbox_events()) == 2

    def fail_enqueue(*_args, **_kwargs):
        raise RuntimeError("forced outbox insert failure")

    monkeypatch.setattr(
        "app.services.workflow_commands.enqueue_application_workflow_event",
        fail_enqueue,
    )
    with TestClient(app, raise_server_exceptions=False) as local_client:
        failed_response = local_client.post(
            f"/hr/applications/{application['id']}/advance",
            json={
                "targetStage": "shortlisted",
                "expectedVersion": review_response.json()["version"],
            },
            headers=hr_headers,
        )
    assert failed_response.status_code == 500
    latest = client.get(f"/hr/applications/{application['id']}", headers=hr_headers)
    assert latest.status_code == 200
    assert latest.json()["status"] == "under_review"
    assert latest.json()["version"] == 2
    assert count_rows(models.ApplicationStatusHistory) == 2
    assert len(outbox_events()) == 2


def test_enqueue_event_reuses_existing_deduplication_key_and_database_rejects_duplicate():
    db = SessionLocal()
    try:
        first = enqueue_event(
            db,
            event_type="job.published.v1",
            aggregate_type="job",
            aggregate_id=1,
            aggregate_version=2,
            command_name="publish",
            data={"fromStatus": "draft", "toStatus": "published", "companyId": "1"},
        )
        second = enqueue_event(
            db,
            event_type="job.published.v1",
            aggregate_type="job",
            aggregate_id=1,
            aggregate_version=2,
            command_name="publish",
            data={"fromStatus": "draft", "toStatus": "published", "companyId": "1"},
        )
        assert second.id == first.id
        duplicate = models.OutboxEvent(
            id="00000000-0000-0000-0000-000000000001",
            event_type=first.event_type,
            schema_version=first.schema_version,
            aggregate_type=first.aggregate_type,
            aggregate_id=first.aggregate_id,
            aggregate_version=first.aggregate_version,
            command_name=first.command_name,
            causation_id="00000000-0000-0000-0000-000000000002",
            correlation_id=None,
            deduplication_key=first.deduplication_key,
            payload=first.payload,
            status=OUTBOX_STATUS_PENDING,
            attempts=0,
            available_at=utc_now(),
            occurred_at=utc_now(),
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_dispatcher_publish_retry_dead_requeue_and_cleanup():
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
        db.commit()
        event_id = event.id
    finally:
        db.close()

    publisher = RecordingOutboxPublisher()
    assert (
        run_once(
            publisher=publisher,
            worker_id="test-worker",
            batch_size=10,
            lease_seconds=30,
            max_attempts=3,
            base_delay_seconds=1,
            max_delay_seconds=5,
        )
        == 1
    )
    assert len(publisher.published) == 1
    db = SessionLocal()
    try:
        published = db.get(models.OutboxEvent, event_id)
        assert published is not None
        assert published.status == OUTBOX_STATUS_PUBLISHED
        assert published.published_at is not None
        assert published.locked_by is None
    finally:
        db.close()

    db = SessionLocal()
    try:
        retry_event = enqueue_event(
            db,
            event_type="job.reopened.v1",
            aggregate_type="job",
            aggregate_id=8,
            aggregate_version=4,
            command_name="reopen",
            data={"fromStatus": "closed", "toStatus": "published", "companyId": "1"},
        )
        db.commit()
        retry_event_id = retry_event.id
    finally:
        db.close()

    failing = RecordingOutboxPublisher(fail_first=1)
    assert (
        run_once(
            publisher=failing,
            worker_id="test-worker",
            batch_size=10,
            lease_seconds=30,
            max_attempts=3,
            base_delay_seconds=1,
            max_delay_seconds=5,
        )
        == 1
    )
    db = SessionLocal()
    try:
        retry_row = db.get(models.OutboxEvent, retry_event_id)
        assert retry_row is not None
        assert retry_row.status == OUTBOX_STATUS_PENDING
        assert retry_row.attempts == 1
        assert retry_row.available_at > retry_row.occurred_at
        assert retry_row.last_error == "publish failed"
    finally:
        db.close()

    db = SessionLocal()
    try:
        dead_event = enqueue_event(
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
        db.commit()
        dead_event_id = dead_event.id
    finally:
        db.close()

    dead_publisher = RecordingOutboxPublisher(fail_first=1)
    assert (
        run_once(
            publisher=dead_publisher,
            worker_id="test-worker",
            batch_size=10,
            lease_seconds=30,
            max_attempts=1,
            base_delay_seconds=1,
            max_delay_seconds=5,
        )
        == 1
    )
    db = SessionLocal()
    try:
        dead_row = db.get(models.OutboxEvent, dead_event_id)
        assert dead_row is not None
        assert dead_row.status == OUTBOX_STATUS_DEAD
        assert requeue_dead_event(db, event_id=dead_event_id)
        db.commit()
        requeued = db.get(models.OutboxEvent, dead_event_id)
        assert requeued is not None
        assert requeued.status == OUTBOX_STATUS_PENDING
        requeued.status = OUTBOX_STATUS_DEAD
        old_published = db.get(models.OutboxEvent, event_id)
        assert old_published is not None
        old_published.published_at = utc_now()
        recent_published = enqueue_event(
            db,
            event_type="application.withdrawn.v1",
            aggregate_type="job_application",
            aggregate_id=10,
            aggregate_version=2,
            command_name="withdraw",
            data={
                "fromStatus": "submitted",
                "toStatus": "withdrawn",
                "jobId": "7",
                "candidateUserId": "4",
            },
        )
        recent_published.status = OUTBOX_STATUS_PUBLISHED
        recent_published.published_at = utc_now()
        db.commit()
        deleted = cleanup_published_events(
            db,
            older_than=utc_now(),
            batch_size=1,
        )
        db.commit()
        assert deleted == 1
        assert db.get(models.OutboxEvent, dead_event_id) is not None
        assert db.get(models.OutboxEvent, recent_published.id) is not None
    finally:
        db.close()


def test_dispatcher_marks_non_retryable_transport_failure_dead_immediately():
    db = SessionLocal()
    try:
        event = enqueue_event(
            db,
            event_type="application.rejected.v1",
            aggregate_type="job_application",
            aggregate_id=91,
            aggregate_version=2,
            command_name="reject",
            data={
                "fromStatus": "submitted",
                "toStatus": "rejected",
                "jobId": "7",
                "candidateUserId": "3",
            },
        )
        db.commit()
        event_id = event.id
    finally:
        db.close()

    publisher = RecordingOutboxPublisher(
        fail_first=1,
        failure_message="invalid event envelope",
        retryable=False,
        error_category="invalid_event",
    )

    assert (
        run_once(
            publisher=publisher,
            worker_id="test-worker",
            batch_size=10,
            lease_seconds=30,
            max_attempts=10,
            base_delay_seconds=1,
            max_delay_seconds=5,
        )
        == 1
    )

    db = SessionLocal()
    try:
        dead_row = db.get(models.OutboxEvent, event_id)
        assert dead_row is not None
        assert dead_row.status == OUTBOX_STATUS_DEAD
        assert dead_row.attempts == 1
        assert dead_row.last_error == "invalid event envelope"
    finally:
        db.close()
