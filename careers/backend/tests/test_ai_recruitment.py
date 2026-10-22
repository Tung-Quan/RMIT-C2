from unittest.mock import AsyncMock, patch

from app.db import models
from app.db.database import SessionLocal
from app.workers.processing_worker import run_once

JOB_PROFILE = {"criteria": [{"name": "Python", "importance": "required"}]}


def register_and_login(client, *, email, role, full_name):
    client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": full_name,
            "password": "Strong!Pass123",
            "role": role,
        },
    )
    login_response = client.post(
        "/auth/login",
        json={"email": email, "password": "Strong!Pass123"},
    )
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def setup_hr_and_company(client):
    hr_headers = register_and_login(
        client,
        email="hr-matching@example.com",
        role="hr",
        full_name="Matching HR",
    )
    client.post(
        "/companies",
        json={
            "name": "Matching Company",
            "description": "Company for matching testing.",
            "industry": "Technology",
        },
        headers=hr_headers,
    )
    return hr_headers


def run_worker_once(*, batch_size: int = 10) -> int:
    return run_once(
        worker_id="test-processing-worker",
        batch_size=batch_size,
        lease_seconds=60,
        base_delay_seconds=0,
        max_delay_seconds=0,
    )


def create_parsed_job(client, headers, *, title: str = "Backend Dev") -> dict:
    response = client.post(
        "/hr/jobs",
        json={
            "title": title,
            "description": "Backend APIs and services.",
            "requirements": "Python",
            "responsibilities": "Build APIs",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    job = response.json()

    with patch(
        "app.services.processing_executors.parse_job_description",
        new_callable=AsyncMock,
    ) as mock_ai:
        mock_ai.return_value = JOB_PROFILE
        assert run_worker_once() == 1

    with SessionLocal() as db:
        stored = db.get(models.JobPosting, job["id"])
        assert stored is not None
        assert stored.ai_parse_status == "completed"
        assert stored.ai_parsed_profile == JOB_PROFILE
        job["ai_parse_revision"] = stored.ai_parse_revision
        job["version"] = stored.version
    return job


def create_completed_cv_application(job_id: int, candidate_email: str) -> int:
    with SessionLocal() as db:
        candidate_user = db.query(models.User).filter_by(email=candidate_email).first()
        assert candidate_user is not None
        application = models.JobApplication(
            job_posting_id=job_id,
            candidate_user_id=candidate_user.id,
            status="submitted",
            ai_cv_parse_status="completed",
            ai_cv_parse_revision=1,
            ai_cv_parsed_profile={
                "evidence_items": [{"name": "Python Exp", "evidence_type": "experience"}]
            },
        )
        db.add(application)
        db.commit()
        db.refresh(application)
        return application.id


def test_hr_rerank_stores_sorted_candidate_results(client):
    hr_headers = setup_hr_and_company(client)
    job = create_parsed_job(client, hr_headers)
    register_and_login(
        client,
        email="cand1@example.com",
        role="candidate",
        full_name="Cand 1",
    )
    application_id = create_completed_cv_application(job["id"], "cand1@example.com")

    rerank_resp = client.post(f"/hr/jobs/{job['id']}/rerank", headers=hr_headers)
    assert rerank_resp.status_code == 202, rerank_resp.text
    rerank_payload = rerank_resp.json()
    run_id = rerank_payload["rerank_run"]["id"]
    processing_job = rerank_payload["processing_job"]
    assert processing_job["job_type"] == "application_rerank"
    assert processing_job["status"] == "queued"

    provider_result = {
        "model_name": "qwen",
        "results": [
            {
                "application_id": application_id,
                "criterion_results": [
                    {
                        "criterion_index": 0,
                        "criterion_name": "Python",
                        "importance": "required",
                        "status": "matched",
                        "explanation": "Matches.",
                        "evidence_text": "Python Exp",
                        "internal_evidence_score": 0.9,
                    }
                ],
            }
        ],
    }
    with patch(
        "app.services.processing_executors._call_matching_provider",
        return_value=provider_result,
    ):
        assert run_worker_once() == 1

    status_resp = client.get(
        f"/processing-jobs/{processing_job['id']}",
        headers=hr_headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "succeeded"

    list_resp = client.get(f"/hr/jobs/{job['id']}/reranks", headers=hr_headers)
    list_data = list_resp.json()
    assert list_data[0]["id"] == run_id
    assert list_data[0]["status"] == "completed"
    assert len(list_data[0]["application_results"]) == 1
    assert list_data[0]["application_results"][0]["job_application_id"] == application_id


def test_stale_job_revision_cannot_publish_rerank_results(client):
    hr_headers = setup_hr_and_company(client)
    job = create_parsed_job(client, hr_headers, title="Test Stale")

    rerank_resp = client.post(f"/hr/jobs/{job['id']}/rerank", headers=hr_headers)
    assert rerank_resp.status_code == 202, rerank_resp.text
    run_id = rerank_resp.json()["rerank_run"]["id"]
    rerank_processing_job_id = rerank_resp.json()["processing_job"]["id"]

    update_response = client.put(
        f"/hr/jobs/{job['id']}",
        json={"expectedVersion": job["version"], "requirements": "Python, Java"},
        headers=hr_headers,
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["ai_parse_status"] == "pending"

    with SessionLocal() as db:
        db.query(models.AsyncProcessingJob).filter(
            models.AsyncProcessingJob.id != rerank_processing_job_id,
            models.AsyncProcessingJob.status == "queued",
        ).update(
            {models.AsyncProcessingJob.status: "cancelled"},
            synchronize_session=False,
        )
        db.commit()

    assert run_worker_once(batch_size=1) == 1

    status_resp = client.get(
        f"/processing-jobs/{rerank_processing_job_id}",
        headers=hr_headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "failed"
    assert status_resp.json()["last_error_code"] == "stale_source_data"

    list_resp = client.get(f"/hr/jobs/{job['id']}/reranks", headers=hr_headers)
    run = [item for item in list_resp.json() if item["id"] == run_id][0]
    assert run["status"] == "failed"


def test_rerank_authorization_visibility_and_unavailable_candidates(client):
    hr_headers = setup_hr_and_company(client)
    job = create_parsed_job(client, hr_headers, title="Auth Job")

    candidate_headers = register_and_login(
        client,
        email="hack@example.com",
        role="candidate",
        full_name="Hacker",
    )

    assert client.post(f"/hr/jobs/{job['id']}/rerank", headers=candidate_headers).status_code == 403
    assert client.get(f"/hr/jobs/{job['id']}/reranks", headers=candidate_headers).status_code == 403

    with SessionLocal() as db:
        hack_user = db.query(models.User).filter_by(email="hack@example.com").first()
        assert hack_user is not None
        application = models.JobApplication(
            job_posting_id=job["id"],
            candidate_user_id=hack_user.id,
            status="submitted",
            ai_cv_parse_status="pending",
            ai_cv_parse_revision=1,
        )
        db.add(application)
        db.commit()

    rerank_resp = client.post(f"/hr/jobs/{job['id']}/rerank", headers=hr_headers)
    assert rerank_resp.status_code == 202, rerank_resp.text
    run_id = rerank_resp.json()["rerank_run"]["id"]
    processing_job_id = rerank_resp.json()["processing_job"]["id"]

    hidden_response = client.get(
        f"/processing-jobs/{processing_job_id}",
        headers=candidate_headers,
    )
    assert hidden_response.status_code == 404

    assert run_worker_once() == 1

    list_resp = client.get(f"/hr/jobs/{job['id']}/reranks", headers=hr_headers)
    run = [item for item in list_resp.json() if item["id"] == run_id][0]
    assert run["status"] == "completed"
    assert run["application_results"] == []
