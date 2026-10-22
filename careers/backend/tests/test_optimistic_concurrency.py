from prometheus_client import generate_latest

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


def create_company(client, headers, *, name="Optimistic Labs"):
    response = client.post(
        "/companies",
        json={
            "name": name,
            "description": "Tests optimistic concurrency.",
            "website": None,
            "industry": "Technology",
            "location": "Singapore",
            "logo_url": None,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_job(client, headers, *, status="draft", title="Versioned Backend Intern"):
    response = client.post(
        "/hr/jobs",
        json={
            "title": title,
            "description": "Work on reliable FastAPI APIs.",
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
        files={"file": ("cv.txt", b"FastAPI optimistic concurrency", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def setup_job_application_flow(client):
    hr_headers = register_and_login(
        client,
        email="optimistic-hr@example.edu",
        role="hr",
        full_name="Optimistic HR",
    )
    create_company(client, hr_headers)
    job = create_job(client, hr_headers, status="published")

    candidate_headers = register_and_login(
        client,
        email="optimistic-candidate@example.edu",
        full_name="Optimistic Candidate",
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


def get_application_history_count() -> int:
    db = SessionLocal()
    try:
        return db.query(models.ApplicationStatusHistory).count()
    finally:
        db.close()


def advance_application(client, headers, application_id, *, version, target_stage):
    response = client.post(
        f"/hr/applications/{application_id}/advance",
        json={"targetStage": target_stage, "expectedVersion": version},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def test_job_update_requires_expected_version_and_increments_once(client):
    hr_headers = register_and_login(
        client,
        email="job-version-hr@example.edu",
        role="hr",
        full_name="Job Version HR",
    )
    create_company(client, hr_headers)
    job = create_job(client, hr_headers)

    assert job["version"] == 1

    update_response = client.put(
        f"/hr/jobs/{job['id']}",
        json={"title": "Updated Backend Intern", "expectedVersion": job["version"]},
        headers=hr_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Updated Backend Intern"
    assert update_response.json()["version"] == 2

    stale_response = client.put(
        f"/hr/jobs/{job['id']}",
        json={"title": "Stale Backend Intern", "expectedVersion": job["version"]},
        headers=hr_headers,
    )
    assert stale_response.status_code == 409
    assert stale_response.json()["detail"]["code"] == "stale_version"
    assert stale_response.json()["detail"]["currentVersion"] == 2

    get_response = client.get(f"/hr/jobs/{job['id']}", headers=hr_headers)
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Updated Backend Intern"
    assert get_response.json()["version"] == 2

    missing_response = client.patch(
        f"/hr/jobs/{job['id']}/status",
        json={"status": "published"},
        headers=hr_headers,
    )
    assert missing_response.status_code == 422


def test_application_status_update_stale_conflict_and_retry(client):
    hr_headers, _candidate_headers, _job, application = setup_job_application_flow(client)
    assert application["version"] == 1
    assert get_application_history_count() == 1

    update_response = client.post(
        f"/hr/applications/{application['id']}/advance",
        json={
            "targetStage": "under_review",
            "note": "Strong backend profile.",
            "expectedVersion": application["version"],
        },
        headers=hr_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "under_review"
    assert update_response.json()["version"] == 2
    assert update_response.json()["status_history"][-1]["old_status"] == "submitted"
    assert get_application_history_count() == 2

    stale_response = client.post(
        f"/hr/applications/{application['id']}/advance",
        json={"targetStage": "shortlisted", "expectedVersion": application["version"]},
        headers=hr_headers,
    )
    assert stale_response.status_code == 409
    assert stale_response.json()["detail"]["code"] == "stale_version"
    assert stale_response.json()["detail"]["currentVersion"] == 2
    assert get_application_history_count() == 2

    latest_response = client.get(f"/hr/applications/{application['id']}", headers=hr_headers)
    retry_response = client.post(
        f"/hr/applications/{application['id']}/advance",
        json={
            "targetStage": "shortlisted",
            "expectedVersion": latest_response.json()["version"],
        },
        headers=hr_headers,
    )
    assert retry_response.status_code == 200
    assert retry_response.json()["status"] == "shortlisted"
    assert retry_response.json()["version"] == 3
    assert get_application_history_count() == 3


def test_candidate_withdraw_uses_version_and_blocks_terminal_states(client):
    hr_headers, candidate_headers, _job, application = setup_job_application_flow(client)

    under_review = advance_application(
        client,
        hr_headers,
        application["id"],
        version=application["version"],
        target_stage="under_review",
    )
    shortlisted = advance_application(
        client,
        hr_headers,
        application["id"],
        version=under_review["version"],
        target_stage="shortlisted",
    )
    interview = advance_application(
        client,
        hr_headers,
        application["id"],
        version=shortlisted["version"],
        target_stage="interview",
    )
    offered = advance_application(
        client,
        hr_headers,
        application["id"],
        version=interview["version"],
        target_stage="offered",
    )

    withdraw_response = client.post(
        f"/candidate/job-applications/{application['id']}/withdraw",
        json={"expectedVersion": offered["version"]},
        headers=candidate_headers,
    )
    assert withdraw_response.status_code == 409
    assert withdraw_response.json()["detail"]["code"] == "invalid_state_transition"
    assert withdraw_response.json()["detail"]["currentStatus"] == "offered"
    assert get_application_history_count() == 5


def test_stale_conflict_does_not_leak_to_unauthorized_hr(client):
    owner_headers = register_and_login(
        client,
        email="owner-version-hr@example.edu",
        role="hr",
        full_name="Owner Version HR",
    )
    create_company(client, owner_headers, name="Owner Version Co")
    job = create_job(client, owner_headers)

    other_headers = register_and_login(
        client,
        email="other-version-hr@example.edu",
        role="hr",
        full_name="Other Version HR",
    )
    create_company(client, other_headers, name="Other Version Co")

    response = client.put(
        f"/hr/jobs/{job['id']}",
        json={"title": "Unauthorized Update", "expectedVersion": 999},
        headers=other_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "You do not have access to this job"


def test_optimistic_concurrency_metrics_use_bounded_labels(client):
    hr_headers = register_and_login(
        client,
        email="optimistic-metrics-hr@example.edu",
        role="hr",
        full_name="Optimistic Metrics HR",
    )
    create_company(client, hr_headers)
    job = create_job(client, hr_headers)

    client.post(
        f"/hr/jobs/{job['id']}/publish",
        json={"expectedVersion": job["version"]},
        headers=hr_headers,
    )
    client.post(
        f"/hr/jobs/{job['id']}/close",
        json={"expectedVersion": job["version"]},
        headers=hr_headers,
    )

    metrics_text = generate_latest().decode("utf-8")
    assert "workflow_command_total" in metrics_text
    assert 'resource_type="job"' in metrics_text
    assert 'command="publish"' in metrics_text
    assert 'command="close"' in metrics_text
    assert 'outcome="success"' in metrics_text
    assert 'outcome="stale"' in metrics_text
