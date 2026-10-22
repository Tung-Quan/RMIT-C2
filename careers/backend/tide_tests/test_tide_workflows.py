"""Run with an isolated SQLite database; never connects to the live app database.

The gateway's EdDSA/DPoP boundary is tested separately by tests/gateway.test.mjs.
These tests exercise the private assertion and copied FastAPI business rules.
"""
import hashlib
import json
import os
import tempfile
import time
import uuid

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["FAIRENROL_GATEWAY_SECRET"] = "isolated-migration-test-secret-not-a-deployment-secret"
os.environ["LOCAL_UPLOAD_DIR"] = tempfile.mkdtemp(prefix="fairenrol-tide-tests-")
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import database

test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
database.engine = test_engine
database.SessionLocal = sessionmaker(bind=test_engine)

from app.db import models
from app.main import app


@pytest.fixture
def client():
    models.Base.metadata.drop_all(bind=test_engine)
    with TestClient(app) as client:
        yield client


def prepare(client, method, path, *, person="candidate-test", role="candidate", **kwargs):
    request = client.build_request(method, path, **kwargs)
    body = request.read()
    now = int(time.time())
    payload = {
        "iss": "fairenrol-careers-gateway", "aud": "careers-api",
        "sub": person, "person_id": person, "tide_issuer": "urn:isolated:tide-test",
        "tide_subject": person, "full_name": "Synthetic " + person, "role": role,
        "email": None, "iat": now, "exp": now + 30, "jti": str(uuid.uuid4()),
        "method": method, "path": request.url.raw_path.decode(),
        "body_sha256": hashlib.sha256(body).hexdigest(),
    }
    request.headers["Authorization"] = "Bearer " + jwt.encode(payload, os.environ["FAIRENROL_GATEWAY_SECRET"], algorithm="HS256")
    return request


def call(client, method, path, **kwargs):
    return client.send(prepare(client, method, path, **kwargs))


def test_private_api_rejects_unsigned_requests_and_password_routes(client):
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/login", json={"email": "unused@example.invalid", "password": "unused"}).status_code == 401
    assert call(client, "POST", "/auth/register", json={}).status_code == 404


def test_subject_binding_does_not_invent_an_email_or_duplicate_users(client):
    first = call(client, "GET", "/auth/me").json()
    second = call(client, "GET", "/auth/me").json()
    assert first["id"] == second["id"]
    assert first["email"] is None
    assert first["role"] == "candidate"


def test_assertions_are_single_use_and_bound_to_request_body(client):
    request = prepare(client, "GET", "/auth/me")
    assert client.send(request).status_code == 200
    assert client.send(request).status_code == 401
    request = prepare(client, "POST", "/companies", role="hr", json={"name": "Untampered"})
    altered = client.build_request("POST", "/companies", content=b'{"name":"tampered"}', headers=dict(request.headers))
    assert client.send(altered).status_code == 401


def test_invalid_role_and_cross_audience_assertions_fail(client):
    assert client.send(prepare(client, "GET", "/auth/me", role="admin")).status_code == 401
    request = prepare(client, "GET", "/auth/me")
    claims = jwt.get_unverified_claims(request.headers["Authorization"][7:])
    claims["aud"] = "careers-chat-connect"
    request.headers["Authorization"] = "Bearer " + jwt.encode(claims, os.environ["FAIRENROL_GATEWAY_SECRET"], algorithm="HS256")
    assert client.send(request).status_code == 401


def test_candidate_cannot_create_company_or_hijack_an_hr_job(client):
    assert call(client, "POST", "/companies", json={"name": "Forbidden"}).status_code == 403
    company = call(client, "POST", "/companies", person="hr-owner", role="hr", json={"name": "Local Test Company"})
    assert company.status_code == 201
    job = call(client, "POST", "/hr/jobs", person="hr-owner", role="hr", json={"title": "Synthetic FairEnrol role", "description": "Synthetic local test position"})
    assert job.status_code == 201
    assert call(client, "GET", f'/hr/jobs/{job.json()["id"]}', person="other-hr", role="hr").status_code in {403, 404}


def test_tide_identity_can_complete_the_preserved_application_workflow(client):
    hr = {"person": "hr-owner", "role": "hr"}
    assert call(client, "POST", "/companies", **hr, json={"name": "Local Test Company"}).status_code == 201
    response = call(client, "POST", "/hr/jobs", **hr, json={"title": "Synthetic FairEnrol role", "description": "Python APIs and SQL. Synthetic local test only.", "requirements": "Python", "status": "draft"})
    assert response.status_code == 201, response.text
    job = response.json()
    published = call(client, "POST", f'/hr/jobs/{job["id"]}/publish', **hr, json={"expectedVersion": job["version"]})
    assert published.status_code == 200, published.text
    tracker = call(client, "POST", "/applications", json={"company_name": "Local Test Company", "position_title": "Synthetic FairEnrol role", "job_description": "Python APIs"})
    assert tracker.status_code == 201
    cv = b"Synthetic candidate. Python, React, SQL. Local test document; no real personal data."
    uploaded = call(client, "POST", f'/applications/{tracker.json()["id"]}/documents', data={"document_type": "CV"}, files={"file": ("synthetic_cv.txt", cv, "text/plain")})
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    assert call(client, "GET", f"/documents/{document_id}/content").content == cv
    assert call(client, "GET", f"/documents/{document_id}/content", person="other-candidate").status_code in {403, 404}
    applied = call(client, "POST", f'/jobs/{job["id"]}/apply', json={"document_ids": [document_id], "candidate_note": "Synthetic test"})
    assert applied.status_code in {200, 201}, applied.text
    application = applied.json()
    duplicate = call(client, "POST", f'/jobs/{job["id"]}/apply', json={"document_ids": [document_id]})
    assert duplicate.status_code == 409
    advanced = call(client, "POST", f'/hr/applications/{application["id"]}/advance', **hr, json={"expectedVersion": application["version"], "targetStage": "under_review", "note": "Synthetic workflow verification"})
    assert advanced.status_code == 200, advanced.text
    stale = call(client, "POST", f'/hr/applications/{application["id"]}/advance', **hr, json={"expectedVersion": application["version"], "targetStage": "shortlisted"})
    assert stale.status_code == 409
    with database.SessionLocal() as db:
        assert db.query(models.OutboxEvent).count() > 0


def test_local_user_deactivation_remains_enforced(client):
    user = call(client, "GET", "/auth/me").json()
    with database.SessionLocal() as db:
        db.get(models.User, user["id"]).is_active = False
        db.commit()
    assert call(client, "GET", "/auth/me").status_code == 401


def test_hiring_staff_can_read_their_own_candidate_document_status(client):
    hr = {"person": "hr-owner", "role": "hr"}
    tracker = call(client, "POST", "/applications", **hr, json={"company_name": "Demo", "position_title": "Demo", "job_description": "Synthetic local test"}).json()
    uploaded = call(client, "POST", f'/applications/{tracker["id"]}/documents', **hr, data={"document_type": "CV"}, files={"file": ("own.txt", b"Synthetic local test document", "text/plain")}).json()
    status = call(client, "GET", f'/documents/{uploaded["id"]}/extracted-text-status', **hr)
    assert status.status_code == 404
    assert status.json()["detail"] == "Document text has not been extracted"
    # The owner may start asynchronous extraction before this CV is attached to any job.
    assert call(client, "POST", f'/documents/{uploaded["id"]}/extract-text', **hr).status_code == 202


def test_utf8_cv_files_accepted_by_the_ui_are_available_to_the_ai_pipeline(client):
    from pathlib import Path
    from app.services.document_text_service import build_document_text_data
    root = Path(os.environ["LOCAL_UPLOAD_DIR"])
    (root / "unicode.txt").write_text("SYNTHETIC CV\nSkills: Python, React, SQL.\nA university student project.", encoding="utf-8-sig")
    parsed = build_document_text_data(file_name="unicode.txt", s3_key="unicode.txt")
    assert parsed.status == "succeeded"
    assert parsed.parser_name == "utf8-text"
    assert "Python" in parsed.raw_text and parsed.blocks_json
    (root / "binary.txt").write_bytes(b"\xff\xfe\x00")
    assert build_document_text_data(file_name="binary.txt", s3_key="binary.txt").status == "failed"
    assert build_document_text_data(file_name="document.docx", s3_key="document.docx").status == "unsupported"
