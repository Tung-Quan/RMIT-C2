from pathlib import Path

from app.db import models
from app.db.database import SessionLocal
from app.workers.processing_worker import run_once


def run_worker_once(*, batch_size: int = 10) -> int:
    return run_once(
        worker_id="test-document-worker",
        batch_size=batch_size,
        lease_seconds=60,
        base_delay_seconds=0,
        max_delay_seconds=0,
    )


def cancel_processing_jobs_except(job_id: str) -> None:
    with SessionLocal() as db:
        db.query(models.AsyncProcessingJob).filter(
            models.AsyncProcessingJob.id != job_id,
            models.AsyncProcessingJob.status.in_(("queued", "running")),
        ).update(
            {models.AsyncProcessingJob.status: "cancelled"},
            synchronize_session=False,
        )
        db.commit()


def auth_headers(client, email="docs@example.edu", role="candidate"):
    client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": "Document Tester",
            "password": "Strong!Pass123",
            "role": role,
        },
    )
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "Strong!Pass123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_application(client, headers):
    response = client.post(
        "/applications",
        json={
            "company_name": "CloudCo",
            "position_title": "Cloud Intern",
            "job_description": "Python FastAPI AWS S3 Docker role.",
            "application_status": "Saved",
            "deadline": None,
            "notes": None,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def upload_document(client, application_id, headers, filename="cv.txt", content=b"Python AWS S3"):
    return client.post(
        f"/applications/{application_id}/documents",
        data={"document_type": "CV"},
        files={"file": (filename, content, "text/plain")},
        headers=headers,
    )


def test_upload_list_download_url_and_delete_document(client):
    headers = auth_headers(client)
    application = create_application(client, headers)

    upload_response = upload_document(client, application["id"], headers)
    assert upload_response.status_code == 201
    document = upload_response.json()
    assert document["document_type"] == "CV"

    with SessionLocal() as db:
        stored_document = db.get(models.Document, document["id"])
        assert stored_document is not None
        assert stored_document.s3_key
        assert stored_document.file_url is not None
        assert stored_document.file_url.startswith("/uploads/")
        stored_path = Path(".test_uploads") / str(stored_document.s3_key)

    assert stored_path.exists()

    list_response = client.get(
        f"/applications/{application['id']}/documents",
        headers=headers,
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    download_response = client.get(
        f"/documents/{document['id']}/download-url",
        headers=headers,
    )
    assert download_response.status_code == 200
    download_payload = download_response.json()
    assert download_payload["document_id"] == document["id"]
    assert download_payload["download_url"].startswith("/uploads/")

    delete_response = client.delete(f"/documents/{document['id']}", headers=headers)
    assert delete_response.status_code == 200
    assert not stored_path.exists()

    list_after_delete = client.get(
        f"/applications/{application['id']}/documents",
        headers=headers,
    )
    assert list_after_delete.status_code == 200
    assert list_after_delete.json() == []


def test_candidate_direct_document_upload_creates_reusable_document(client):
    headers = auth_headers(client)

    upload_response = client.post(
        "/candidate/documents",
        data={"document_type": "CV"},
        files={"file": ("direct_cv.txt", b"Python FastAPI AWS", "text/plain")},
        headers=headers,
    )

    assert upload_response.status_code == 201
    document = upload_response.json()
    assert document["document_type"] == "CV"
    assert document["file_name"] == "direct_cv.txt"
    assert document["application_id"]

    applications_response = client.get("/applications", headers=headers)
    assert applications_response.status_code == 200
    assert applications_response.json() == []

    update_response = client.put(
        f"/applications/{document['application_id']}",
        json={
            "company_name": "Edited",
            "position_title": "Edited",
            "job_description": "Edited",
        },
        headers=headers,
    )
    assert update_response.status_code == 400

    delete_response = client.delete(
        f"/applications/{document['application_id']}",
        headers=headers,
    )
    assert delete_response.status_code == 400

    list_response = client.get("/candidate/documents", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == document["id"]


def test_document_upload_rejects_invalid_type_and_extension(client):
    headers = auth_headers(client)
    application = create_application(client, headers)

    invalid_type_response = client.post(
        f"/applications/{application['id']}/documents",
        data={"document_type": "Resume"},
        files={"file": ("cv.txt", b"Python AWS", "text/plain")},
        headers=headers,
    )
    assert invalid_type_response.status_code == 400

    invalid_extension_response = client.post(
        f"/applications/{application['id']}/documents",
        data={"document_type": "CV"},
        files={"file": ("cv.exe", b"not allowed", "application/octet-stream")},
        headers=headers,
    )
    assert invalid_extension_response.status_code == 400


def test_document_routes_reject_cross_user_access(client):
    owner_headers = auth_headers(client, "owner@example.edu")
    application = create_application(client, owner_headers)
    upload_response = upload_document(client, application["id"], owner_headers)
    assert upload_response.status_code == 201
    document = upload_response.json()

    other_headers = auth_headers(client, "other@example.edu")

    list_response = client.get(
        f"/applications/{application['id']}/documents",
        headers=other_headers,
    )
    assert list_response.status_code == 403

    download_response = client.get(
        f"/documents/{document['id']}/download-url",
        headers=other_headers,
    )
    assert download_response.status_code == 403

    delete_response = client.delete(
        f"/documents/{document['id']}",
        headers=other_headers,
    )
    assert delete_response.status_code == 403


def test_candidate_can_extract_pdf_text_and_read_cached_result(client, monkeypatch):
    headers = auth_headers(client, "pdf-candidate@example.edu")
    application = create_application(client, headers)
    upload_response = upload_document(
        client,
        application["id"],
        headers,
        filename="cv.pdf",
        content=b"fake pdf bytes",
    )
    assert upload_response.status_code == 201
    document = upload_response.json()

    monkeypatch.setattr(
        "app.services.document_text_service.extract_pdf_pages",
        lambda file_bytes: [
            {
                "page": 1,
                "text": (
                    "SUMMARY\nBackend intern candidate\n"
                    "PROJECTS\n- Built FastAPI APIs with PostgreSQL\n"
                    "- Deployed services on AWS\n"
                    "EDUCATION\nExample University"
                ),
            }
        ],
    )

    extract_response = client.post(
        f"/documents/{document['id']}/extract-text",
        headers=headers,
    )
    assert extract_response.status_code == 202
    payload = extract_response.json()
    assert payload["job_type"] == "document_text_extraction"
    assert payload["status"] == "queued"

    assert run_worker_once() == 1

    processing_response = client.get(
        f"/processing-jobs/{payload['id']}",
        headers=headers,
    )
    assert processing_response.status_code == 200
    assert processing_response.json()["status"] == "succeeded"

    cached_response = client.post(
        f"/documents/{document['id']}/extract-text",
        headers=headers,
    )
    assert cached_response.status_code == 200
    payload = cached_response.json()
    assert payload["extraction_status"] == "succeeded"
    assert payload["skipped_cached"] is True
    assert "FastAPI" in payload["raw_text"]
    assert payload["blocks_json"]
    assert {group["group_name"] for group in payload["semantic_groups_json"]}

    status_response = client.get(
        f"/documents/{document['id']}/extracted-text-status",
        headers=headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["text_hash"]

    text_response = client.get(f"/documents/{document['id']}/text", headers=headers)
    assert text_response.status_code == 200
    assert text_response.json()["semantic_groups_json"]


def test_non_pdf_document_extraction_is_unsupported(client):
    headers = auth_headers(client, "unsupported-candidate@example.edu")
    application = create_application(client, headers)
    upload_response = upload_document(client, application["id"], headers)
    assert upload_response.status_code == 201
    document = upload_response.json()

    extract_response = client.post(
        f"/documents/{document['id']}/extract-text",
        headers=headers,
    )
    assert extract_response.status_code == 202
    processing_job = extract_response.json()
    assert processing_job["job_type"] == "document_text_extraction"

    assert run_worker_once() == 1

    processing_response = client.get(
        f"/processing-jobs/{processing_job['id']}",
        headers=headers,
    )
    assert processing_response.status_code == 200
    assert processing_response.json()["status"] == "failed"
    assert processing_response.json()["last_error_code"] == "unsupported_document_type"

    status_response = client.get(
        f"/documents/{document['id']}/extracted-text-status",
        headers=headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["extraction_status"] == "unsupported"


def test_hr_can_extract_attached_cv_text_and_bulk_extract_applicants(client, monkeypatch):
    hr_headers = auth_headers(client, "text-hr@example.edu", role="hr")
    company_response = client.post(
        "/companies",
        json={
            "name": "Text Labs",
            "description": "Text extraction tests.",
            "website": None,
            "industry": "Technology",
            "location": "Singapore",
            "logo_url": None,
        },
        headers=hr_headers,
    )
    assert company_response.status_code == 201

    job_response = client.post(
        "/hr/jobs",
        json={
            "title": "Backend Intern",
            "description": "Build backend APIs.",
            "requirements": None,
            "responsibilities": None,
            "location": "Singapore",
            "employment_type": "early_career",
            "work_mode": "hybrid",
            "salary_min": 0,
            "salary_max": 0,
            "deadline": "2026-12-31",
            "status": "published",
        },
        headers=hr_headers,
    )
    assert job_response.status_code == 201
    job = job_response.json()

    candidate_headers = auth_headers(client, "text-candidate@example.edu")
    application = create_application(client, candidate_headers)
    upload_response = upload_document(
        client,
        application["id"],
        candidate_headers,
        filename="submitted_cv.pdf",
        content=b"fake pdf bytes",
    )
    assert upload_response.status_code == 201
    document = upload_response.json()

    apply_response = client.post(
        f"/jobs/{job['id']}/apply",
        json={
            "cover_letter_text": None,
            "candidate_note": None,
            "document_ids": [document["id"]],
        },
        headers=candidate_headers,
    )
    assert apply_response.status_code == 201

    monkeypatch.setattr(
        "app.services.document_text_service.extract_pdf_pages",
        lambda file_bytes: [
            {
                "page": 1,
                "text": "PROJECTS\n- Built FastAPI APIs\nEDUCATION\nExample University",
            }
        ],
    )

    other_hr_headers = auth_headers(client, "other-text-hr@example.edu", role="hr")
    forbidden_response = client.post(
        f"/documents/{document['id']}/extract-text",
        headers=other_hr_headers,
    )
    assert forbidden_response.status_code == 404

    extract_response = client.post(
        f"/documents/{document['id']}/extract-text",
        headers=hr_headers,
    )
    assert extract_response.status_code == 202
    extract_job = extract_response.json()
    cancel_processing_jobs_except(extract_job["id"])

    assert run_worker_once() == 1

    status_response = client.get(
        f"/documents/{document['id']}/extracted-text-status",
        headers=hr_headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["extraction_status"] == "succeeded"

    bulk_response = client.post(
        f"/hr/jobs/{job['id']}/applicants/extract-text",
        headers=hr_headers,
    )
    assert bulk_response.status_code == 200
    bulk_payload = bulk_response.json()
    assert bulk_payload["total_documents"] == 1
    assert bulk_payload["skipped_cached"] == 1
