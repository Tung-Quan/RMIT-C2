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


def create_company(client, headers, *, name="Workflow Labs"):
    response = client.post(
        "/companies",
        json={
            "name": name,
            "description": "Tests workflow commands.",
            "website": None,
            "industry": "Technology",
            "location": "Singapore",
            "logo_url": None,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_job(client, headers, *, status="draft", title="Workflow Backend Intern"):
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
        files={"file": ("cv.txt", b"FastAPI workflow commands", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def setup_job_application_flow(client, *, email_prefix="workflow"):
    hr_headers = register_and_login(
        client,
        email=f"{email_prefix}-hr@example.edu",
        role="hr",
        full_name="Workflow HR",
    )
    create_company(client, hr_headers, name=f"{email_prefix} Company")
    job = create_job(client, hr_headers, status="published")

    candidate_headers = register_and_login(
        client,
        email=f"{email_prefix}-candidate@example.edu",
        full_name="Workflow Candidate",
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


def count_rows(model: type[object]) -> int:
    db = SessionLocal()
    try:
        return db.query(model).count()
    finally:
        db.close()


def test_job_commands_enforce_transitions_and_idempotent_replay(client):
    hr_headers = register_and_login(
        client,
        email="workflow-job-hr@example.edu",
        role="hr",
        full_name="Workflow Job HR",
    )
    create_company(client, hr_headers)
    job = create_job(client, hr_headers)

    publish_response = client.post(
        f"/hr/jobs/{job['id']}/publish",
        json={"expectedVersion": job["version"]},
        headers={**hr_headers, "Idempotency-Key": "publish-job-key"},
    )
    assert publish_response.status_code == 200
    assert publish_response.json()["status"] == "published"
    assert publish_response.json()["version"] == 2

    replay_response = client.post(
        f"/hr/jobs/{job['id']}/publish",
        json={"expectedVersion": job["version"]},
        headers={**hr_headers, "Idempotency-Key": "publish-job-key"},
    )
    assert replay_response.status_code == 200
    assert replay_response.headers["Idempotency-Replayed"] == "true"
    assert replay_response.json() == publish_response.json()

    mismatch_response = client.post(
        f"/hr/jobs/{job['id']}/publish",
        json={"expectedVersion": publish_response.json()["version"]},
        headers={**hr_headers, "Idempotency-Key": "publish-job-key"},
    )
    assert mismatch_response.status_code == 409
    assert mismatch_response.json()["detail"]["code"] == "idempotency_key_reused"

    republish_response = client.post(
        f"/hr/jobs/{job['id']}/publish",
        json={"expectedVersion": publish_response.json()["version"]},
        headers=hr_headers,
    )
    assert republish_response.status_code == 409
    assert republish_response.json()["detail"]["code"] == "invalid_state_transition"
    assert republish_response.json()["detail"]["currentState"] == "published"
    assert republish_response.json()["detail"]["requestedCommand"] == "publish"

    close_response = client.post(
        f"/hr/jobs/{job['id']}/close",
        json={"expectedVersion": publish_response.json()["version"]},
        headers=hr_headers,
    )
    assert close_response.status_code == 200
    assert close_response.json()["status"] == "closed"
    assert close_response.json()["version"] == 3

    reopen_response = client.post(
        f"/hr/jobs/{job['id']}/reopen",
        json={"expectedVersion": close_response.json()["version"]},
        headers=hr_headers,
    )
    assert reopen_response.status_code == 200
    assert reopen_response.json()["status"] == "published"
    assert reopen_response.json()["version"] == 4


def test_job_commands_reject_unauthorized_and_invalid_close(client):
    owner_headers = register_and_login(
        client,
        email="workflow-owner-hr@example.edu",
        role="hr",
        full_name="Workflow Owner HR",
    )
    create_company(client, owner_headers, name="Workflow Owner Co")
    draft_job = create_job(client, owner_headers)

    other_headers = register_and_login(
        client,
        email="workflow-other-hr@example.edu",
        role="hr",
        full_name="Workflow Other HR",
    )
    create_company(client, other_headers, name="Workflow Other Co")

    unauthorized_response = client.post(
        f"/hr/jobs/{draft_job['id']}/publish",
        json={"expectedVersion": draft_job["version"]},
        headers=other_headers,
    )
    assert unauthorized_response.status_code == 403

    close_draft_response = client.post(
        f"/hr/jobs/{draft_job['id']}/close",
        json={"expectedVersion": draft_job["version"]},
        headers=owner_headers,
    )
    assert close_draft_response.status_code == 409
    assert close_draft_response.json()["detail"]["code"] == "invalid_state_transition"
    assert close_draft_response.json()["detail"]["currentState"] == "draft"


def test_safe_delete_and_archive_policy_preserves_applications(client):
    hr_headers = register_and_login(
        client,
        email="workflow-delete-hr@example.edu",
        role="hr",
        full_name="Workflow Delete HR",
    )
    create_company(client, hr_headers)
    draft_job = create_job(client, hr_headers, title="Disposable Draft")

    delete_response = client.post(
        f"/hr/jobs/{draft_job['id']}/delete-draft",
        json={"expectedVersion": draft_job["version"]},
        headers=hr_headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"
    assert client.get(f"/hr/jobs/{draft_job['id']}", headers=hr_headers).status_code == 404

    _hr_headers, _candidate_headers, active_job, application = setup_job_application_flow(
        client,
        email_prefix="workflow-archive",
    )
    hard_delete_response = client.delete(
        f"/hr/jobs/{active_job['id']}",
        params={"expectedVersion": active_job["version"]},
        headers=_hr_headers,
    )
    assert hard_delete_response.status_code == 409
    assert hard_delete_response.headers["Deprecation"] == "true"
    assert count_rows(models.JobApplication) == 1

    archive_response = client.post(
        f"/hr/jobs/{active_job['id']}/archive",
        json={"expectedVersion": active_job["version"]},
        headers=_hr_headers,
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "closed"
    assert archive_response.json()["version"] == active_job["version"] + 1
    assert count_rows(models.JobApplication) == 1

    application_response = client.get(
        f"/hr/applications/{application['id']}",
        headers=_hr_headers,
    )
    assert application_response.status_code == 200
    assert application_response.json()["job_posting"]["status"] == "closed"


def test_application_advance_reject_and_legacy_status_delegation(client):
    hr_headers, _candidate_headers, _job, application = setup_job_application_flow(
        client,
        email_prefix="workflow-application",
    )

    review_response = client.post(
        f"/hr/applications/{application['id']}/advance",
        json={"targetStage": "under_review", "expectedVersion": application["version"]},
        headers=hr_headers,
    )
    assert review_response.status_code == 200
    assert review_response.json()["status"] == "under_review"
    assert review_response.json()["version"] == 2
    assert count_rows(models.ApplicationStatusHistory) == 2

    invalid_skip = client.post(
        f"/hr/applications/{application['id']}/advance",
        json={"targetStage": "interview", "expectedVersion": review_response.json()["version"]},
        headers=hr_headers,
    )
    assert invalid_skip.status_code == 409
    assert invalid_skip.json()["detail"]["code"] == "invalid_state_transition"
    assert invalid_skip.json()["detail"]["currentState"] == "under_review"
    assert count_rows(models.ApplicationStatusHistory) == 2

    legacy_response = client.patch(
        f"/hr/applications/{application['id']}/status",
        json={
            "status": "shortlisted",
            "note": "Legacy delegate.",
            "expectedVersion": review_response.json()["version"],
        },
        headers=hr_headers,
    )
    assert legacy_response.status_code == 200
    assert legacy_response.headers["Deprecation"] == "true"
    assert legacy_response.json()["status"] == "shortlisted"
    assert count_rows(models.ApplicationStatusHistory) == 3

    reject_response = client.post(
        f"/hr/applications/{application['id']}/reject",
        json={"reason": "Position requirements changed.", "expectedVersion": 3},
        headers=hr_headers,
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"
    assert reject_response.json()["version"] == 4
    assert reject_response.json()["status_history"][-1]["note"] == (
        "Position requirements changed."
    )


def test_candidate_withdraw_command_authorization_and_terminal_state(client):
    hr_headers, candidate_headers, _job, application = setup_job_application_flow(
        client,
        email_prefix="workflow-withdraw",
    )
    other_candidate_headers = register_and_login(
        client,
        email="workflow-other-candidate@example.edu",
        full_name="Other Candidate",
    )

    unauthorized_response = client.post(
        f"/candidate/job-applications/{application['id']}/withdraw",
        json={"expectedVersion": application["version"]},
        headers=other_candidate_headers,
    )
    assert unauthorized_response.status_code == 403

    withdraw_response = client.post(
        f"/candidate/job-applications/{application['id']}/withdraw",
        json={"expectedVersion": application["version"]},
        headers=candidate_headers,
    )
    assert withdraw_response.status_code == 200
    assert withdraw_response.json()["status"] == "withdrawn"
    assert withdraw_response.json()["version"] == 2
    assert count_rows(models.ApplicationStatusHistory) == 2

    reject_response = client.post(
        f"/hr/applications/{application['id']}/reject",
        json={"reason": "Too late.", "expectedVersion": withdraw_response.json()["version"]},
        headers=hr_headers,
    )
    assert reject_response.status_code == 409
    assert reject_response.json()["detail"]["code"] == "invalid_state_transition"
    assert reject_response.json()["detail"]["currentState"] == "withdrawn"
    assert count_rows(models.ApplicationStatusHistory) == 2
