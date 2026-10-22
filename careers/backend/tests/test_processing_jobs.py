from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.db import models
from app.db.database import SessionLocal
from app.services.processing_jobs import (
    JOB_TYPE_CV_PARSE,
    JOB_TYPE_DOCUMENT_TEXT_EXTRACTION,
    JOB_TYPE_JOB_DESCRIPTION_PARSE,
    PROCESSING_STATUS_FAILED,
    PROCESSING_STATUS_QUEUED,
    PROCESSING_STATUS_RUNNING,
    claim_processing_jobs,
    enqueue_processing_job,
    mark_processing_job_retry_or_failed,
)
from app.workers.processing_worker import run_once


def auth_headers(client, email, role="candidate"):
    client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": "Strong!Pass123",
            "role": role,
        },
    )
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "Strong!Pass123"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_hr_company(client, headers):
    response = client.post(
        "/companies",
        json={
            "name": "Processing Labs",
            "description": "Queue tests.",
            "industry": "Technology",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


def create_published_job_without_parse(client, headers):
    response = client.post(
        "/hr/jobs",
        json={
            "title": "Queue Intern",
            "description": "Work on queues.",
            "requirements": None,
            "responsibilities": None,
            "status": "published",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_tracker_application(client, headers):
    response = client.post(
        "/applications",
        json={
            "company_name": "QueueCo",
            "position_title": "Intern",
            "job_description": "Queues and APIs.",
            "application_status": "Saved",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload_cv_document(client, headers, application_id):
    response = client.post(
        f"/applications/{application_id}/documents",
        data={"document_type": "CV"},
        files={"file": ("cv.pdf", b"fake pdf bytes", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_candidate_apply_enqueues_cv_parse_job_and_status_is_scoped(client):
    hr_headers = auth_headers(client, "processing-hr@example.edu", role="hr")
    create_hr_company(client, hr_headers)
    job = create_published_job_without_parse(client, hr_headers)

    candidate_headers = auth_headers(client, "processing-candidate@example.edu")
    tracker = create_tracker_application(client, candidate_headers)
    document = upload_cv_document(client, candidate_headers, tracker["id"])

    apply_response = client.post(
        f"/jobs/{job['id']}/apply",
        json={"document_ids": [document["id"]]},
        headers=candidate_headers,
    )
    assert apply_response.status_code == 201, apply_response.text
    application_id = apply_response.json()["id"]

    with SessionLocal() as db:
        processing_job = (
            db.query(models.AsyncProcessingJob)
            .filter(
                models.AsyncProcessingJob.job_type == JOB_TYPE_CV_PARSE,
                models.AsyncProcessingJob.related_entity_id == str(application_id),
            )
            .one()
        )
        processing_job_id = processing_job.id
        assert processing_job.status == PROCESSING_STATUS_QUEUED
        assert processing_job.owner_user_id == processing_job.requester_user_id

    status_response = client.get(
        f"/processing-jobs/{processing_job_id}",
        headers=candidate_headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["job_type"] == JOB_TYPE_CV_PARSE

    other_candidate_headers = auth_headers(client, "processing-other@example.edu")
    hidden_response = client.get(
        f"/processing-jobs/{processing_job_id}",
        headers=other_candidate_headers,
    )
    assert hidden_response.status_code == 404


def test_idempotent_candidate_apply_replay_does_not_enqueue_duplicate_processing_job(client):
    hr_headers = auth_headers(client, "processing-idem-hr@example.edu", role="hr")
    create_hr_company(client, hr_headers)
    job = create_published_job_without_parse(client, hr_headers)

    candidate_headers = auth_headers(client, "processing-idem-candidate@example.edu")
    tracker = create_tracker_application(client, candidate_headers)
    document = upload_cv_document(client, candidate_headers, tracker["id"])
    payload = {"document_ids": [document["id"]]}
    headers = {**candidate_headers, "Idempotency-Key": "processing-apply-key"}

    first_response = client.post(f"/jobs/{job['id']}/apply", json=payload, headers=headers)
    replay_response = client.post(f"/jobs/{job['id']}/apply", json=payload, headers=headers)

    assert first_response.status_code == 201, first_response.text
    assert replay_response.status_code == 201, replay_response.text
    assert replay_response.headers["Idempotency-Replayed"] == "true"
    assert replay_response.json()["id"] == first_response.json()["id"]
    assert replay_response.json()["status"] == "submitted"
    assert replay_response.json()["version"] == first_response.json()["version"]

    with SessionLocal() as db:
        applications = db.query(models.JobApplication).all()
        processing_jobs = (
            db.query(models.AsyncProcessingJob)
            .filter(models.AsyncProcessingJob.job_type == JOB_TYPE_CV_PARSE)
            .all()
        )
        assert len(applications) == 1
        assert len(processing_jobs) == 1
        assert processing_jobs[0].related_entity_id == str(first_response.json()["id"])


def test_downstream_processing_failure_does_not_undo_submitted_application(client):
    hr_headers = auth_headers(client, "processing-failure-hr@example.edu", role="hr")
    create_hr_company(client, hr_headers)
    job = create_published_job_without_parse(client, hr_headers)

    candidate_headers = auth_headers(client, "processing-failure-candidate@example.edu")
    tracker = create_tracker_application(client, candidate_headers)
    document = upload_cv_document(client, candidate_headers, tracker["id"])

    apply_response = client.post(
        f"/jobs/{job['id']}/apply",
        json={"document_ids": [document["id"]]},
        headers=candidate_headers,
    )
    assert apply_response.status_code == 201, apply_response.text
    application_id = apply_response.json()["id"]

    assert (
        run_once(
            worker_id="test-failure-worker",
            batch_size=1,
            lease_seconds=60,
            base_delay_seconds=0,
            max_delay_seconds=0,
        )
        == 1
    )

    detail_response = client.get(
        f"/candidate/job-applications/{application_id}",
        headers=candidate_headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == application_id
    assert detail_response.json()["status"] == "submitted"
    assert detail_response.json()["version"] == 1

    with SessionLocal() as db:
        application = db.get(models.JobApplication, application_id)
        assert application is not None
        assert application.status == "submitted"
        assert application.ai_cv_parse_status == "failed"
        failed_job = (
            db.query(models.AsyncProcessingJob)
            .filter(
                models.AsyncProcessingJob.job_type == JOB_TYPE_CV_PARSE,
                models.AsyncProcessingJob.related_entity_id == str(application_id),
            )
            .one()
        )
        assert failed_job.status == PROCESSING_STATUS_FAILED


def test_processing_claim_retry_terminal_failure_and_expired_lease_reclaim():
    now = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)

    with SessionLocal() as db:
        retry_job = enqueue_processing_job(
            db,
            job_type=JOB_TYPE_DOCUMENT_TEXT_EXTRACTION,
            deduplication_key="processing:test:retry",
            input_json={"document_id": 123},
            owner_user_id=None,
            requester_user_id=None,
            related_entity_type="document",
            related_entity_id=123,
            source_entity_type="document",
            source_entity_id=123,
            source_version=None,
            max_attempts=2,
            now=now,
        )
        retry_job_id = retry_job.id
        db.commit()

    with SessionLocal() as db:
        claimed = claim_processing_jobs(
            db,
            worker_id="worker-a",
            batch_size=1,
            lease_seconds=30,
            now=now,
        )
        db.commit()
    assert [job.job_id for job in claimed] == [retry_job_id]

    with SessionLocal() as db:
        outcome = mark_processing_job_retry_or_failed(
            db,
            job_id=retry_job_id,
            error_code="provider_unavailable",
            error_message="temporary",
            retryable=True,
            base_delay_seconds=0,
            max_delay_seconds=0,
            now=now,
        )
        db.commit()
    assert outcome == "retry"

    with SessionLocal() as db:
        claimed_again = claim_processing_jobs(
            db,
            worker_id="worker-b",
            batch_size=1,
            lease_seconds=30,
            now=now,
        )
        db.commit()
    assert [job.job_id for job in claimed_again] == [retry_job_id]

    with SessionLocal() as db:
        outcome = mark_processing_job_retry_or_failed(
            db,
            job_id=retry_job_id,
            error_code="provider_unavailable",
            error_message="still down",
            retryable=True,
            base_delay_seconds=0,
            max_delay_seconds=0,
            now=now,
        )
        db.commit()
    assert outcome == "failed"

    with SessionLocal() as db:
        failed_job = db.get(models.AsyncProcessingJob, retry_job_id)
        assert failed_job is not None
        assert failed_job.status == PROCESSING_STATUS_FAILED
        assert failed_job.attempts == 2

        lease_job = enqueue_processing_job(
            db,
            job_type=JOB_TYPE_DOCUMENT_TEXT_EXTRACTION,
            deduplication_key="processing:test:lease",
            input_json={"document_id": 456},
            owner_user_id=None,
            requester_user_id=None,
            related_entity_type="document",
            related_entity_id=456,
            source_entity_type="document",
            source_entity_id=456,
            source_version=None,
            now=now,
        )
        lease_job_id = lease_job.id
        db.commit()

    with SessionLocal() as db:
        first_claim = claim_processing_jobs(
            db,
            worker_id="worker-a",
            batch_size=1,
            lease_seconds=30,
            now=now,
        )
        db.commit()
    assert [job.job_id for job in first_claim] == [lease_job_id]

    with SessionLocal() as db:
        blocked_claim = claim_processing_jobs(
            db,
            worker_id="worker-b",
            batch_size=1,
            lease_seconds=30,
            now=now + timedelta(seconds=10),
        )
        db.commit()
    assert blocked_claim == []

    with SessionLocal() as db:
        reclaimed_claim = claim_processing_jobs(
            db,
            worker_id="worker-b",
            batch_size=1,
            lease_seconds=30,
            now=now + timedelta(seconds=31),
        )
        db.commit()
    assert [job.job_id for job in reclaimed_claim] == [lease_job_id]

    with SessionLocal() as db:
        lease_row = db.get(models.AsyncProcessingJob, lease_job_id)
        assert lease_row is not None
        assert lease_row.status == PROCESSING_STATUS_RUNNING
        assert lease_row.locked_by == "worker-b"


def test_job_parse_worker_fails_stale_revision_without_overwriting_newer_state(client):
    hr_headers = auth_headers(client, "stale-parse-hr@example.edu", role="hr")
    create_hr_company(client, hr_headers)
    response = client.post(
        "/hr/jobs",
        json={
            "title": "Stale Parse",
            "description": "Build APIs.",
            "requirements": "Python",
            "responsibilities": "Ship services",
        },
        headers=hr_headers,
    )
    assert response.status_code == 201, response.text
    job_id = response.json()["id"]

    with SessionLocal() as db:
        job = db.get(models.JobPosting, job_id)
        assert job is not None
        job.ai_parse_revision += 1
        job.ai_parse_status = "pending"
        current_revision = job.ai_parse_revision
        processing_job = (
            db.query(models.AsyncProcessingJob)
            .filter(models.AsyncProcessingJob.job_type == JOB_TYPE_JOB_DESCRIPTION_PARSE)
            .one()
        )
        processing_job_id = processing_job.id
        db.commit()

    with patch(
        "app.services.processing_executors.parse_job_description",
        new_callable=AsyncMock,
    ) as mock_ai:
        assert (
            run_once(
                worker_id="test-stale-worker",
                batch_size=1,
                lease_seconds=60,
                base_delay_seconds=0,
                max_delay_seconds=0,
            )
            == 1
        )
        mock_ai.assert_not_called()

    status_response = client.get(
        f"/processing-jobs/{processing_job_id}",
        headers=hr_headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == PROCESSING_STATUS_FAILED
    assert status_response.json()["last_error_code"] == "stale_source_data"

    with SessionLocal() as db:
        job = db.get(models.JobPosting, job_id)
        assert job is not None
        assert job.ai_parse_revision == current_revision
        assert job.ai_parse_status == "pending"
        assert job.ai_parsed_profile is None
