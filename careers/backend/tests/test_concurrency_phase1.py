from app.db import models
from app.db.database import SessionLocal


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
            "name": "Concurrency Labs",
            "description": "Tests data integrity.",
            "website": None,
            "industry": "Technology",
            "location": "Ho Chi Minh City",
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
            "title": "Backend Reliability Intern",
            "description": "Work on FastAPI and DynamoDB workflows.",
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


def test_duplicate_register_returns_409(client):
    payload = {
        "email": "duplicate@example.edu",
        "full_name": "Duplicate User",
        "password": "Strong!Pass123",
        "role": "candidate",
    }

    first_response = client.post("/auth/register", json=payload)
    second_response = client.post("/auth/register", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_duplicate_company_create_returns_409(client):
    headers = register_and_login(
        client,
        email="company-owner@example.edu",
        role="hr",
        full_name="Company Owner",
    )

    create_company(client, headers)
    duplicate_response = client.post(
        "/companies",
        json={"name": "Second Profile"},
        headers=headers,
    )

    assert duplicate_response.status_code == 409


def test_duplicate_job_apply_returns_409_and_keeps_single_application(client):
    hr_headers = register_and_login(
        client,
        email="apply-hr@example.edu",
        role="hr",
        full_name="Apply HR",
    )
    create_company(client, hr_headers)
    job = create_published_job(client, hr_headers)

    candidate_headers = register_and_login(
        client,
        email="apply-candidate@example.edu",
        full_name="Apply Candidate",
    )
    tracker = create_tracker_application(client, candidate_headers)
    document = upload_document(client, candidate_headers, tracker["id"])
    payload = {
        "cover_letter_text": "Please consider me.",
        "candidate_note": None,
        "document_ids": [document["id"]],
    }

    first_response = client.post(
        f"/jobs/{job['id']}/apply",
        json=payload,
        headers=candidate_headers,
    )
    second_response = client.post(
        f"/jobs/{job['id']}/apply",
        json=payload,
        headers=candidate_headers,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409

    db = SessionLocal()
    try:
        assert db.query(models.JobApplication).count() == 1
    finally:
        db.close()


def test_apply_rejects_duplicate_document_ids_before_unique_attachment_conflict(client):
    hr_headers = register_and_login(
        client,
        email="duplicate-doc-hr@example.edu",
        role="hr",
        full_name="Duplicate Doc HR",
    )
    create_company(client, hr_headers)
    job = create_published_job(client, hr_headers)

    candidate_headers = register_and_login(
        client,
        email="duplicate-doc-candidate@example.edu",
        full_name="Duplicate Doc Candidate",
    )
    tracker = create_tracker_application(client, candidate_headers)
    document = upload_document(client, candidate_headers, tracker["id"])

    response = client.post(
        f"/jobs/{job['id']}/apply",
        json={
            "cover_letter_text": "Please consider me.",
            "candidate_note": None,
            "document_ids": [document["id"], document["id"]],
        },
        headers=candidate_headers,
    )

    assert response.status_code == 422
