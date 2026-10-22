import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.db import models
from app.db.database import SessionLocal
from app.services.processing_jobs import (
    JOB_TYPE_DOCUMENT_TEXT_EXTRACTION,
    PROCESSING_STATUS_RUNNING,
    PROCESSING_STATUS_SUCCEEDED,
    claim_processing_jobs,
    enqueue_processing_job,
    utc_now,
)
from app.workers.processing_worker import run_once

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def require_postgres_database():
    if not os.environ.get("POSTGRES_TEST_DATABASE_URL"):
        pytest.skip("POSTGRES_TEST_DATABASE_URL is required for PostgreSQL integration tests")


def create_processing_job(deduplication_key: str) -> str:
    db = SessionLocal()
    try:
        job = enqueue_processing_job(
            db,
            job_type=JOB_TYPE_DOCUMENT_TEXT_EXTRACTION,
            deduplication_key=deduplication_key,
            input_json={"document_id": deduplication_key},
            owner_user_id=None,
            requester_user_id=None,
            related_entity_type="document",
            related_entity_id=deduplication_key,
            source_entity_type="document",
            source_entity_id=deduplication_key,
            source_version=None,
        )
        job_id = job.id
        db.commit()
        return job_id
    finally:
        db.close()


def claim_ids(worker_id: str, *, batch_size: int = 10, now=None) -> list[str]:
    db = SessionLocal()
    try:
        jobs = claim_processing_jobs(
            db,
            worker_id=worker_id,
            batch_size=batch_size,
            lease_seconds=30,
            now=now,
        )
        ids = [job.job_id for job in jobs]
        db.commit()
        return ids
    finally:
        db.close()


def processing_rows() -> list[models.AsyncProcessingJob]:
    db = SessionLocal()
    try:
        rows = (
            db.query(models.AsyncProcessingJob)
            .order_by(models.AsyncProcessingJob.created_at.asc())
            .all()
        )
        for row in rows:
            db.expunge(row)
        return rows
    finally:
        db.close()


def test_postgres_workers_claim_distinct_processing_jobs_without_double_claim():
    created_ids = [create_processing_job(f"pg-processing-claim-{index}") for index in range(4)]

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = list(
            executor.map(
                lambda worker_id: claim_ids(worker_id, batch_size=3),
                ["worker-a", "worker-b"],
            )
        )

    flattened = [job_id for batch in claimed for job_id in batch]
    assert sorted(flattened) == sorted(created_ids)
    assert len(flattened) == len(set(flattened))
    rows = processing_rows()
    assert {row.status for row in rows} == {PROCESSING_STATUS_RUNNING}
    assert {row.locked_by for row in rows} == {"worker-a", "worker-b"}


def test_postgres_active_processing_lease_blocks_and_expired_lease_reclaims():
    job_id = create_processing_job("pg-processing-lease")
    now = utc_now()

    assert claim_ids("worker-a", now=now) == [job_id]
    assert claim_ids("worker-b", now=now + timedelta(seconds=10)) == []
    assert claim_ids("worker-b", now=now + timedelta(seconds=31)) == [job_id]

    rows = processing_rows()
    assert rows[0].locked_by == "worker-b"


def test_postgres_claim_commits_before_slow_provider_and_api_writes_continue(client):
    job_id = create_processing_job("pg-processing-slow-provider")
    provider_entered = threading.Event()
    provider_release = threading.Event()

    def slow_executor(_job):
        provider_entered.set()
        assert provider_release.wait(timeout=10)
        return {"ok": True}

    with ThreadPoolExecutor(max_workers=1) as executor:
        with patch(
            "app.workers.processing_worker.execute_processing_job", side_effect=slow_executor
        ):
            future = executor.submit(
                run_once,
                worker_id="worker-slow",
                batch_size=1,
                lease_seconds=60,
                base_delay_seconds=0,
                max_delay_seconds=0,
            )
            assert provider_entered.wait(timeout=10)

            with SessionLocal() as db:
                running_job = db.get(models.AsyncProcessingJob, job_id)
                assert running_job is not None
                assert running_job.status == PROCESSING_STATUS_RUNNING
                assert running_job.locked_by == "worker-slow"

            response = client.post(
                "/auth/register",
                json={
                    "email": "processing-unrelated-write@example.edu",
                    "full_name": "Unrelated Writer",
                    "password": "Strong!Pass123",
                    "role": "candidate",
                },
            )
            assert response.status_code == 201, response.text

            provider_release.set()
            assert future.result(timeout=10) == 1

    with SessionLocal() as db:
        completed = db.get(models.AsyncProcessingJob, job_id)
        assert completed is not None
        assert completed.status == PROCESSING_STATUS_SUCCEEDED
        assert db.query(models.User).filter_by(email="processing-unrelated-write@example.edu").one()


def test_postgres_unexpired_running_job_cannot_be_stolen_under_parallel_claims():
    job_id = create_processing_job("pg-processing-no-steal")
    now = utc_now()
    assert claim_ids("worker-owner", now=now) == [job_id]

    with ThreadPoolExecutor(max_workers=2) as executor:
        stolen = list(
            executor.map(
                lambda worker_id: claim_ids(worker_id, now=now + timedelta(seconds=5)),
                ["worker-thief-a", "worker-thief-b"],
            )
        )

    assert stolen == [[], []]
    rows = processing_rows()
    assert rows[0].locked_by == "worker-owner"
