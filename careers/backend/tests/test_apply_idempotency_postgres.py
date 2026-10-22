import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db import models
from app.db.database import SessionLocal
from app.main import app

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


def create_company(client, headers):
    response = client.post(
        "/companies",
        json={
            "name": "Postgres Idempotency Labs",
            "description": "Tests idempotent candidate apply on PostgreSQL.",
            "website": None,
            "industry": "Technology",
            "location": "Singapore",
            "logo_url": None,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_published_job(client, headers):
    response = client.post(
        "/hr/jobs",
        json={
            "title": "Postgres Backend Intern",
            "description": "Work on reliable FastAPI workflows.",
            "requirements": "Python and SQL",
            "responsibilities": "Build reliable APIs",
            "location": "Remote",
            "employment_type": "early_career",
            "work_mode": "remote",
            "salary_min": 0,
            "salary_max": 1000,
            "deadline": "2026-12-31",
            "status": "published",
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
        files={"file": ("cv.txt", b"FastAPI PostgreSQL", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def setup_apply_flow(client, *, email: str):
    hr_headers = register_and_login(
        client,
        email=f"hr-{email}",
        role="hr",
        full_name="Postgres HR",
    )
    create_company(client, hr_headers)
    job = create_published_job(client, hr_headers)

    candidate_headers = register_and_login(
        client,
        email=email,
        full_name="Postgres Candidate",
    )
    tracker = create_tracker_application(client, candidate_headers)
    document = upload_document(client, candidate_headers, tracker["id"])
    payload = {
        "cover_letter_text": "Please consider me.",
        "candidate_note": "Available immediately.",
        "document_ids": [document["id"]],
    }
    return job, candidate_headers, payload


def post_apply(job_id: int, headers: dict[str, str], payload: dict[str, Any], key: str):
    with TestClient(app) as local_client:
        return local_client.post(
            f"/jobs/{job_id}/apply",
            json=payload,
            headers={**headers, "Idempotency-Key": key},
        )


def count_rows(model: type[Any]) -> int:
    db = SessionLocal()
    try:
        return db.query(model).count()
    finally:
        db.close()


def logical_attached_documents(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": document["id"],
            "document_id": document["document_id"],
            "document_type": document["document_type"],
            "file_name": document["file_name"],
        }
        for document in response_json["attached_documents"]
    ]


def get_idempotency_record(key: str) -> models.IdempotencyRecord:
    db = SessionLocal()
    try:
        record = (
            db.query(models.IdempotencyRecord)
            .filter(models.IdempotencyRecord.idempotency_key == key)
            .one()
        )
        db.expunge(record)
        return record
    finally:
        db.close()


def test_postgres_concurrent_exact_apply_replay_creates_one_logical_result(client):
    job, headers, payload = setup_apply_flow(client, email="pg-exact@example.edu")

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _index: post_apply(job["id"], headers, payload, "pg-exact-key"),
                range(2),
            )
        )

    assert sorted(response.status_code for response in responses) == [201, 201]
    assert all(response.status_code != 500 for response in responses)
    replay_count = sum(
        response.headers.get("Idempotency-Replayed") == "true" for response in responses
    )
    assert replay_count == 1
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert responses[0].json()["status"] == responses[1].json()["status"]
    assert logical_attached_documents(responses[0].json()) == logical_attached_documents(
        responses[1].json()
    )
    assert count_rows(models.JobApplication) == 1
    assert count_rows(models.IdempotencyRecord) == 1
    assert count_rows(models.ApplicationStatusHistory) == 1
    assert count_rows(models.JobApplicationDocument) == 1

    record = get_idempotency_record("pg-exact-key")
    assert record.status == "completed"
    assert record.response_status == 201
    assert record.resource_id == responses[0].json()["id"]

    db = SessionLocal()
    try:
        cv_parse_jobs = (
            db.query(models.AsyncProcessingJob)
            .filter(
                models.AsyncProcessingJob.job_type == "cv_parse",
                models.AsyncProcessingJob.related_entity_type == "job_application",
                models.AsyncProcessingJob.related_entity_id == str(record.resource_id),
            )
            .all()
        )
        assert len(cv_parse_jobs) == 1
        assert cv_parse_jobs[0].status == "queued"
    finally:
        db.close()


def test_postgres_idempotency_payload_mismatch_returns_409(client):
    job, headers, payload = setup_apply_flow(client, email="pg-mismatch@example.edu")
    changed_payload = {**payload, "candidate_note": "This payload is different."}

    first_response = post_apply(job["id"], headers, payload, "pg-mismatch-key")
    mismatch_response = post_apply(job["id"], headers, changed_payload, "pg-mismatch-key")

    assert first_response.status_code == 201
    assert mismatch_response.status_code == 409
    assert mismatch_response.json()["detail"]["code"] == "idempotency_key_reused"
    assert count_rows(models.JobApplication) == 1


def test_postgres_business_duplicate_with_different_keys_is_replayable(client):
    job, headers, payload = setup_apply_flow(client, email="pg-duplicate@example.edu")

    with ThreadPoolExecutor(max_workers=2) as executor:
        keyed_responses = list(
            executor.map(
                lambda key: (key, post_apply(job["id"], headers, payload, key)),
                ["pg-duplicate-winner", "pg-duplicate-loser"],
            )
        )

    statuses = sorted(response.status_code for _key, response in keyed_responses)
    assert statuses == [201, 409]
    assert count_rows(models.JobApplication) == 1
    assert count_rows(models.ApplicationStatusHistory) == 1
    db = SessionLocal()
    try:
        assert (
            db.query(models.AsyncProcessingJob)
            .filter(models.AsyncProcessingJob.job_type == "cv_parse")
            .count()
            == 1
        )
    finally:
        db.close()

    losing_key = next(key for key, response in keyed_responses if response.status_code == 409)
    losing_response = next(response for key, response in keyed_responses if key == losing_key)
    replay = post_apply(job["id"], headers, payload, losing_key)

    assert losing_response.json()["detail"] == "You have already applied to this job"
    assert replay.status_code == 409
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json() == losing_response.json()


def test_postgres_rollback_after_duplicate_conflict_leaves_database_usable(client):
    job, headers, payload = setup_apply_flow(client, email="pg-rollback@example.edu")

    first_response = post_apply(job["id"], headers, payload, "pg-rollback-first")
    duplicate_response = post_apply(job["id"], headers, payload, "pg-rollback-second")

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert count_rows(models.JobApplication) == 1
    assert count_rows(models.ApplicationStatusHistory) == 1
    assert count_rows(models.JobApplicationDocument) == 1

    db = SessionLocal()
    try:
        assert db.query(models.User).count() == 2
        assert db.query(models.JobApplication).first() is not None
    finally:
        db.close()
