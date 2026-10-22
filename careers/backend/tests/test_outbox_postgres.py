import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import models
from app.db.database import SessionLocal
from app.main import app
from app.services.outbox import (
    OUTBOX_STATUS_DEAD,
    OUTBOX_STATUS_PUBLISHED,
    claim_outbox_events,
    enqueue_event,
    requeue_dead_event,
    utc_now,
)

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def require_postgres_database():
    if not os.environ.get("POSTGRES_TEST_DATABASE_URL"):
        pytest.skip("POSTGRES_TEST_DATABASE_URL is required for PostgreSQL integration tests")


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


def create_company(client, headers, *, name="Postgres Outbox Labs"):
    response = client.post(
        "/companies",
        json={
            "name": name,
            "description": "Tests PostgreSQL outbox concurrency.",
            "website": None,
            "industry": "Technology",
            "location": "Singapore",
            "logo_url": None,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_job(client, headers, *, status="draft", title="Postgres Outbox Intern"):
    response = client.post(
        "/hr/jobs",
        json={
            "title": title,
            "description": "Work on reliable PostgreSQL outbox workflows.",
            "requirements": "Python and SQL",
            "responsibilities": "Build reliable APIs",
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
        files={"file": ("cv.txt", b"FastAPI PostgreSQL outbox", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def setup_application_flow(client):
    hr_headers = register_and_login(
        client,
        email="pg-outbox-hr@example.edu",
        role="hr",
        full_name="Postgres Outbox HR",
    )
    create_company(client, hr_headers)
    job = create_job(client, hr_headers, status="published")
    candidate_headers = register_and_login(
        client,
        email="pg-outbox-candidate@example.edu",
        full_name="Postgres Outbox Candidate",
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
    return hr_headers, job, apply_response.json()


def create_event(
    *,
    aggregate_type: str,
    aggregate_id: int,
    aggregate_version: int,
    event_type: str | None = None,
    command_name: str = "test",
) -> str:
    db = SessionLocal()
    try:
        event = enqueue_event(
            db,
            event_type=event_type or f"{aggregate_type}.test.v1",
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            command_name=command_name,
            data={"value": str(aggregate_version)},
        )
        event_id = event.id
        db.commit()
        return event_id
    finally:
        db.close()


def claim_ids(worker_id: str, *, batch_size: int = 10, now=None) -> list[str]:
    db = SessionLocal()
    try:
        events = claim_outbox_events(
            db,
            worker_id=worker_id,
            batch_size=batch_size,
            lease_seconds=30,
            now=now,
        )
        ids = [event.event_id for event in events]
        db.commit()
        return ids
    finally:
        db.close()


def outbox_rows() -> list[models.OutboxEvent]:
    db = SessionLocal()
    try:
        rows = db.query(models.OutboxEvent).order_by(models.OutboxEvent.created_at.asc()).all()
        for row in rows:
            db.expunge(row)
        return rows
    finally:
        db.close()


def test_postgres_workers_claim_different_available_events():
    created_ids = [
        create_event(aggregate_type="job", aggregate_id=index, aggregate_version=1)
        for index in range(1, 5)
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = list(
            executor.map(
                lambda worker_id: claim_ids(worker_id, batch_size=3),
                ["worker-a", "worker-b"],
            )
        )

    flattened = [event_id for batch in claimed for event_id in batch]
    assert sorted(flattened) == sorted(created_ids)
    assert len(flattened) == len(set(flattened))
    rows = outbox_rows()
    assert {row.status for row in rows} == {"PROCESSING"}
    assert {row.locked_by for row in rows} == {"worker-a", "worker-b"}


def test_postgres_nonexpired_lease_blocks_and_expired_lease_is_reclaimed():
    event_id = create_event(aggregate_type="job", aggregate_id=42, aggregate_version=1)
    now = utc_now()

    assert claim_ids("worker-a", now=now) == [event_id]
    assert claim_ids("worker-b", now=now + timedelta(seconds=10)) == []
    assert claim_ids("worker-b", now=now + timedelta(seconds=31)) == [event_id]

    rows = outbox_rows()
    assert rows[0].locked_by == "worker-b"


def test_postgres_per_aggregate_ordering_and_dead_event_blocking():
    first_id = create_event(
        aggregate_type="job_application",
        aggregate_id=100,
        aggregate_version=1,
        event_type="application.submitted.v1",
    )
    second_id = create_event(
        aggregate_type="job_application",
        aggregate_id=100,
        aggregate_version=2,
        event_type="application.advanced.v1",
    )
    other_id = create_event(
        aggregate_type="job_application",
        aggregate_id=101,
        aggregate_version=1,
        event_type="application.submitted.v1",
    )

    first_claim = claim_ids("worker-a", batch_size=10)
    assert sorted(first_claim) == sorted([first_id, other_id])
    assert second_id not in first_claim

    db = SessionLocal()
    try:
        first = db.get(models.OutboxEvent, first_id)
        assert first is not None
        first.status = OUTBOX_STATUS_DEAD
        first.locked_by = None
        first.locked_at = None
        first.locked_until = None
        db.commit()
    finally:
        db.close()

    assert claim_ids("worker-b", batch_size=10) == []

    db = SessionLocal()
    try:
        assert requeue_dead_event(db, event_id=first_id)
        first = db.get(models.OutboxEvent, first_id)
        assert first is not None
        first.status = OUTBOX_STATUS_PUBLISHED
        first.published_at = utc_now()
        other = db.get(models.OutboxEvent, other_id)
        assert other is not None
        other.status = OUTBOX_STATUS_PUBLISHED
        other.published_at = utc_now()
        db.commit()
    finally:
        db.close()

    assert claim_ids("worker-c", batch_size=10) == [second_id]


def post_application_command(application_id: int, headers: dict[str, str], command: str):
    with TestClient(app) as local_client:
        if command == "advance":
            return command, local_client.post(
                f"/hr/applications/{application_id}/advance",
                json={"targetStage": "under_review", "expectedVersion": 1},
                headers=headers,
            )
        return command, local_client.post(
            f"/hr/applications/{application_id}/reject",
            json={"reason": "Concurrent rejection.", "expectedVersion": 1},
            headers=headers,
        )


def test_postgres_concurrent_application_commands_create_one_transition_event(client):
    hr_headers, _job, application = setup_application_flow(client)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda command: post_application_command(
                    application["id"],
                    hr_headers,
                    command,
                ),
                ["advance", "reject"],
            )
        )

    assert sorted(response.status_code for _command, response in results) == [200, 409]
    transition_events = [
        row
        for row in outbox_rows()
        if row.event_type in {"application.advanced.v1", "application.rejected.v1"}
    ]
    assert len(transition_events) == 1
    assert transition_events[0].aggregate_id == str(application["id"])
    assert transition_events[0].aggregate_version == 2
    assert transition_events[0].payload["data"]["fromStatus"] == "submitted"
    assert transition_events[0].payload["data"]["toStatus"] in {"under_review", "rejected"}

    db = SessionLocal()
    try:
        histories = [
            row
            for row in db.query(models.ApplicationStatusHistory).all()
            if row.job_application_id == application["id"] and row.old_status == "submitted"
        ]
        assert len(histories) == 1
    finally:
        db.close()
