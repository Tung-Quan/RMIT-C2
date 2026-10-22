from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from app.db import models
from app.db.database import SessionLocal
from app.main import app


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
            "name": "Idempotency Labs",
            "description": "Tests idempotent candidate apply.",
            "website": None,
            "industry": "Technology",
            "location": "Singapore",
            "logo_url": None,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_published_job(client, headers, *, title="Idempotent Backend Intern"):
    response = client.post(
        "/hr/jobs",
        json={
            "title": title,
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
        files={"file": ("cv.txt", b"FastAPI DynamoDB", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def setup_apply_flow(client, *, email="apply-idempotent-candidate@example.edu"):
    hr_headers = register_and_login(
        client,
        email=f"hr-{email}",
        role="hr",
        full_name="Idempotent HR",
    )
    create_company(client, hr_headers)
    job = create_published_job(client, hr_headers)

    candidate_headers = register_and_login(
        client,
        email=email,
        full_name="Idempotent Candidate",
    )
    tracker = create_tracker_application(client, candidate_headers)
    document = upload_document(client, candidate_headers, tracker["id"])
    payload = {
        "cover_letter_text": "Please consider me.",
        "candidate_note": "Available immediately.",
        "document_ids": [document["id"]],
    }
    return job, candidate_headers, payload


def post_apply(client, job_id, headers, payload, key):
    return client.post(
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


def contains_key_recursively(value: Any, target: str) -> bool:
    if isinstance(value, dict):
        return target in value or any(
            contains_key_recursively(item, target) for item in value.values()
        )
    if isinstance(value, list):
        return any(contains_key_recursively(item, target) for item in value)
    return False


def test_first_idempotent_apply_creates_application_and_record(client):
    job, headers, payload = setup_apply_flow(client)

    response = post_apply(client, job["id"], headers, payload, "apply-first")

    assert response.status_code == 201
    assert response.headers.get("Idempotency-Replayed") is None
    assert count_rows(models.JobApplication) == 1

    record = get_idempotency_record("apply-first")
    assert record.status == "completed"
    assert record.response_status == 201
    assert record.resource_type == "job_application"
    assert record.resource_id == response.json()["id"]


def test_exact_replay_returns_same_response_and_creates_no_second_application(client):
    job, headers, payload = setup_apply_flow(client, email="replay@example.edu")

    first_response = post_apply(client, job["id"], headers, payload, "apply-replay")
    replay_response = post_apply(client, job["id"], headers, payload, "apply-replay")

    assert first_response.status_code == 201
    assert replay_response.status_code == 201
    assert replay_response.headers["Idempotency-Replayed"] == "true"
    assert replay_response.json() == first_response.json()
    assert count_rows(models.JobApplication) == 1


def test_same_key_with_different_payload_returns_409_without_new_application(client):
    job, headers, payload = setup_apply_flow(client, email="mismatch@example.edu")
    changed_payload = {**payload, "candidate_note": "This is a changed payload."}

    first_response = post_apply(client, job["id"], headers, payload, "apply-mismatch")
    mismatch_response = post_apply(client, job["id"], headers, changed_payload, "apply-mismatch")

    assert first_response.status_code == 201
    assert mismatch_response.status_code == 409
    assert mismatch_response.json()["detail"]["code"] == "idempotency_key_reused"
    assert count_rows(models.JobApplication) == 1


def test_duplicate_application_with_different_key_is_stored_for_replay(client):
    job, headers, payload = setup_apply_flow(client, email="duplicate-new-key@example.edu")

    first_response = post_apply(client, job["id"], headers, payload, "apply-duplicate-first")
    duplicate_response = post_apply(client, job["id"], headers, payload, "apply-duplicate-second")
    duplicate_replay = post_apply(client, job["id"], headers, payload, "apply-duplicate-second")

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "You have already applied to this job"
    assert duplicate_replay.status_code == 409
    assert duplicate_replay.headers["Idempotency-Replayed"] == "true"
    assert duplicate_replay.json() == duplicate_response.json()
    assert count_rows(models.JobApplication) == 1


def test_concurrent_identical_idempotent_apply_creates_one_application(client):
    job, headers, payload = setup_apply_flow(client, email="concurrent@example.edu")

    def send_request():
        with TestClient(app) as local_client:
            return post_apply(local_client, job["id"], headers, payload, "apply-concurrent")

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _index: send_request(), range(2)))

    assert [response.status_code for response in responses] == [201, 201]
    replay_count = sum(
        response.headers.get("Idempotency-Replayed") == "true" for response in responses
    )
    assert replay_count == 1
    assert responses[0].json() == responses[1].json()
    assert count_rows(models.JobApplication) == 1


def test_failed_idempotent_apply_does_not_poison_later_valid_request(client):
    job, headers, payload = setup_apply_flow(client, email="rollback@example.edu")
    invalid_payload = {
        **payload,
        "document_ids": [payload["document_ids"][0], payload["document_ids"][0]],
    }

    invalid_response = post_apply(client, job["id"], headers, invalid_payload, "apply-invalid")
    valid_response = post_apply(client, job["id"], headers, payload, "apply-after-invalid")

    assert invalid_response.status_code == 422
    assert valid_response.status_code == 201
    assert count_rows(models.JobApplication) == 1


def test_stored_success_response_contains_no_sensitive_document_storage_fields(client):
    job, headers, payload = setup_apply_flow(client, email="stored-response@example.edu")

    response = post_apply(client, job["id"], headers, payload, "apply-stored-response")

    assert response.status_code == 201
    stored = get_idempotency_record("apply-stored-response").response_body
    assert not contains_key_recursively(stored, "s3_key")
    assert not contains_key_recursively(stored, "file_url")
    assert not contains_key_recursively(stored, "password")
    assert not contains_key_recursively(stored, "token")


def test_idempotency_metrics_use_bounded_labels(client):
    job, headers, payload = setup_apply_flow(client, email="metrics@example.edu")
    changed_payload = {**payload, "candidate_note": "Changed for metric."}

    post_apply(client, job["id"], headers, payload, "apply-metrics-key")
    post_apply(client, job["id"], headers, payload, "apply-metrics-key")
    post_apply(client, job["id"], headers, changed_payload, "apply-metrics-key")

    metrics_text = generate_latest().decode("utf-8")
    assert 'operation="candidate_apply"' in metrics_text
    assert 'result="reserved"' in metrics_text
    assert 'result="existing"' in metrics_text
    assert "idempotency_replay_total" in metrics_text
    assert "idempotency_mismatch_total" in metrics_text
    assert "apply-metrics-key" not in metrics_text
