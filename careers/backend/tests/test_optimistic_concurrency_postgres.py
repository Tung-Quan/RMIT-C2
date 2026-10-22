import os
from concurrent.futures import ThreadPoolExecutor

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


def create_company(client, headers, *, name="Postgres Optimistic Labs"):
    response = client.post(
        "/companies",
        json={
            "name": name,
            "description": "Tests PostgreSQL optimistic concurrency.",
            "website": None,
            "industry": "Technology",
            "location": "Singapore",
            "logo_url": None,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_job(client, headers, *, status="draft", title="Postgres Versioned Intern"):
    response = client.post(
        "/hr/jobs",
        json={
            "title": title,
            "description": "Work on reliable PostgreSQL workflows.",
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
        files={"file": ("cv.txt", b"FastAPI PostgreSQL versions", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def setup_application_flow(client):
    hr_headers = register_and_login(
        client,
        email="pg-optimistic-hr@example.edu",
        role="hr",
        full_name="Postgres Optimistic HR",
    )
    create_company(client, hr_headers)
    job = create_job(client, hr_headers, status="published")

    candidate_headers = register_and_login(
        client,
        email="pg-optimistic-candidate@example.edu",
        full_name="Postgres Optimistic Candidate",
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
    return hr_headers, candidate_headers, job, apply_response.json()


def close_job(job_id: int, headers: dict[str, str], expected_version: int):
    with TestClient(app) as local_client:
        return local_client.post(
            f"/hr/jobs/{job_id}/close",
            json={"expectedVersion": expected_version},
            headers=headers,
        )


def post_application_command(
    application_id: int,
    headers: dict[str, str],
    command: str,
    expected_version: int,
):
    with TestClient(app) as local_client:
        if command == "advance":
            return command, local_client.post(
                f"/hr/applications/{application_id}/advance",
                json={"targetStage": "under_review", "expectedVersion": expected_version},
                headers=headers,
            )
        return command, local_client.post(
            f"/hr/applications/{application_id}/reject",
            json={"reason": "Concurrent rejection.", "expectedVersion": expected_version},
            headers=headers,
        )


def load_job(job_id: int) -> models.JobPosting:
    db = SessionLocal()
    try:
        job = db.get(models.JobPosting, job_id)
        assert job is not None
        db.expunge(job)
        return job
    finally:
        db.close()


def application_history_rows(application_id: int) -> list[models.ApplicationStatusHistory]:
    db = SessionLocal()
    try:
        rows = (
            db.query(models.ApplicationStatusHistory)
            .filter(models.ApplicationStatusHistory.job_application_id == application_id)
            .order_by(models.ApplicationStatusHistory.created_at.asc())
            .all()
        )
        for row in rows:
            db.expunge(row)
        return rows
    finally:
        db.close()


def load_application(application_id: int) -> models.JobApplication:
    db = SessionLocal()
    try:
        application = db.get(models.JobApplication, application_id)
        assert application is not None
        db.expunge(application)
        return application
    finally:
        db.close()


def test_postgres_concurrent_job_close_allows_one_writer(client):
    hr_headers = register_and_login(
        client,
        email="pg-job-concurrency-hr@example.edu",
        role="hr",
        full_name="Postgres Job HR",
    )
    create_company(client, hr_headers)
    job = create_job(client, hr_headers, status="published")

    assert job["version"] == 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(lambda _index: close_job(job["id"], hr_headers, job["version"]), range(2))
        )

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert all(response.status_code != 500 for response in responses)

    success_response = next(response for response in responses if response.status_code == 200)
    stale_response = next(response for response in responses if response.status_code == 409)

    assert success_response.json()["version"] == 2
    assert stale_response.json()["detail"]["code"] == "stale_version"
    assert stale_response.json()["detail"]["currentVersion"] == 2

    final_job = load_job(job["id"])
    assert final_job.version == 2
    assert final_job.status == "closed"


def test_postgres_concurrent_application_transition_allows_one_history_write(client):
    hr_headers, _candidate_headers, _job, application = setup_application_flow(client)

    assert application["version"] == 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda command: post_application_command(
                    application["id"],
                    hr_headers,
                    command,
                    application["version"],
                ),
                ["advance", "reject"],
            )
        )

    assert sorted(response.status_code for _status, response in results) == [200, 409]
    assert all(response.status_code != 500 for _status, response in results)

    success_command, success_response = next(
        (command, response) for command, response in results if response.status_code == 200
    )
    stale_response = next(response for _status, response in results if response.status_code == 409)

    assert success_response.json()["version"] == 2
    assert stale_response.json()["detail"]["code"] == "stale_version"
    assert stale_response.json()["detail"]["currentVersion"] == 2

    final_application = load_application(application["id"])
    assert final_application.version == 2
    expected_status = "under_review" if success_command == "advance" else "rejected"
    assert final_application.status == expected_status

    history_rows = application_history_rows(application["id"])
    transition_rows = [row for row in history_rows if row.old_status == "submitted"]
    assert len(history_rows) == 2
    assert len(transition_rows) == 1
    assert transition_rows[0].new_status == expected_status

    retry_target = "shortlisted" if final_application.status == "under_review" else "under_review"
    retry_response = client.post(
        f"/hr/applications/{application['id']}/advance",
        json={"targetStage": retry_target, "expectedVersion": final_application.version},
        headers=hr_headers,
    )
    if final_application.status == "under_review":
        assert retry_response.status_code == 200
        assert retry_response.json()["version"] == 3
        assert retry_response.json()["status"] == "shortlisted"
    else:
        assert retry_response.status_code == 409
        assert retry_response.json()["detail"]["code"] == "invalid_state_transition"
