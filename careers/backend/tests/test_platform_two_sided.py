def register_and_login(client, *, email, role, full_name):
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
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_tracker_application(client, headers):
    response = client.post(
        "/applications",
        json={
            "company_name": "Portfolio Co",
            "position_title": "Platform Engineer",
            "job_description": "FastAPI React AWS early-career role.",
            "application_status": "Saved",
            "deadline": None,
            "notes": None,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def upload_candidate_document(client, headers, application_id):
    response = client.post(
        f"/applications/{application_id}/documents",
        data={"document_type": "CV"},
        files={"file": ("candidate_cv.txt", b"Python FastAPI AWS", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_hr_can_create_another_job_with_large_salary(client):
    hr_headers = register_and_login(
        client,
        email="large-salary-hr@example.edu",
        role="hr",
        full_name="Large Salary HR",
    )
    company_response = client.post(
        "/companies",
        json={
            "name": "Large Salary Company",
            "description": "Tests 64-bit salary storage.",
            "website": None,
            "industry": "Technology",
            "location": "Singapore",
            "logo_url": None,
        },
        headers=hr_headers,
    )
    assert company_response.status_code == 201

    base_payload = {
        "description": "A valid full-time role.",
        "requirements": "Relevant experience",
        "responsibilities": "Deliver project work",
        "location": "Singapore",
        "employment_type": "full_time",
        "work_mode": "hybrid",
        "salary_min": 1_111_111,
        "deadline": "2026-08-25",
        "status": "published",
    }
    first_response = client.post(
        "/hr/jobs",
        json={**base_payload, "title": "First Role", "salary_max": 2_000_000},
        headers=hr_headers,
    )
    assert first_response.status_code == 201

    second_response = client.post(
        "/hr/jobs",
        json={**base_payload, "title": "Second Role", "salary_max": 2_222_222_222},
        headers=hr_headers,
    )
    assert second_response.status_code == 201
    assert second_response.json()["salary_max"] == 2_222_222_222


def test_two_sided_job_application_flow(client):
    hr_headers = register_and_login(
        client,
        email="hr@example.edu",
        role="hr",
        full_name="Hiring Manager",
    )

    company_response = client.post(
        "/companies",
        json={
            "name": "Cloud Labs",
            "description": "Cloud career programs.",
            "website": "https://cloudlabs.example",
            "industry": "Technology",
            "location": "Bangkok",
            "logo_url": None,
        },
        headers=hr_headers,
    )
    assert company_response.status_code == 201

    create_job_response = client.post(
        "/hr/jobs",
        json={
            "title": "Backend Engineer",
            "description": "Work on FastAPI APIs.",
            "requirements": "Python, SQL",
            "responsibilities": "Build APIs",
            "location": "Bangkok",
            "employment_type": "early_career",
            "work_mode": "hybrid",
            "salary_min": 1000,
            "salary_max": 2000,
            "deadline": "2026-12-31",
            "status": "draft",
        },
        headers=hr_headers,
    )
    assert create_job_response.status_code == 201
    job = create_job_response.json()

    publish_response = client.post(
        f"/hr/jobs/{job['id']}/publish",
        json={"expectedVersion": job["version"]},
        headers=hr_headers,
    )
    assert publish_response.status_code == 200
    assert publish_response.json()["status"] == "published"
    published_job = publish_response.json()

    candidate_headers = register_and_login(
        client,
        email="candidate@example.edu",
        role="candidate",
        full_name="Student Candidate",
    )
    tracker_application = create_tracker_application(client, candidate_headers)
    document = upload_candidate_document(client, candidate_headers, tracker_application["id"])

    candidate_documents_response = client.get("/candidate/documents", headers=candidate_headers)
    assert candidate_documents_response.status_code == 200
    assert candidate_documents_response.json()[0]["id"] == document["id"]

    jobs_response = client.get("/jobs")
    assert jobs_response.status_code == 200
    assert len(jobs_response.json()) == 1

    apply_response = client.post(
        f"/jobs/{job['id']}/apply",
        json={
            "cover_letter_text": "I would love to join.",
            "candidate_note": "Available immediately.",
            "document_ids": [document["id"]],
        },
        headers=candidate_headers,
    )
    assert apply_response.status_code == 201
    job_application = apply_response.json()
    assert job_application["status"] == "submitted"
    assert len(job_application["attached_documents"]) == 1

    hr_applications_response = client.get(f"/hr/jobs/{job['id']}/applications", headers=hr_headers)
    assert hr_applications_response.status_code == 200
    assert hr_applications_response.json()[0]["candidate_email"] == "candidate@example.edu"

    hr_detail_response = client.get(f"/hr/applications/{job_application['id']}", headers=hr_headers)
    assert hr_detail_response.status_code == 200
    assert hr_detail_response.json()["candidate"]["email"] == "candidate@example.edu"

    hr_documents_response = client.get(
        f"/hr/applications/{job_application['id']}/documents",
        headers=hr_headers,
    )
    assert hr_documents_response.status_code == 200
    assert hr_documents_response.json()[0]["document_id"] == document["id"]

    hr_download_response = client.get(
        f"/hr/documents/{document['id']}/download-url",
        headers=hr_headers,
    )
    assert hr_download_response.status_code == 200
    assert hr_download_response.json()["document_id"] == document["id"]

    review_response = client.post(
        f"/hr/applications/{job_application['id']}/advance",
        json={
            "targetStage": "under_review",
            "note": "Strong backend profile.",
            "expectedVersion": job_application["version"],
        },
        headers=hr_headers,
    )
    assert review_response.status_code == 200
    assert review_response.json()["status"] == "under_review"

    status_response = client.post(
        f"/hr/applications/{job_application['id']}/advance",
        json={
            "targetStage": "shortlisted",
            "note": "Strong backend profile.",
            "expectedVersion": review_response.json()["version"],
        },
        headers=hr_headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "shortlisted"
    reviewed_application = status_response.json()

    candidate_applications_response = client.get(
        "/candidate/job-applications",
        headers=candidate_headers,
    )
    assert candidate_applications_response.status_code == 200
    assert candidate_applications_response.json()[0]["status"] == "shortlisted"

    candidate_detail_response = client.get(
        f"/candidate/job-applications/{job_application['id']}",
        headers=candidate_headers,
    )
    assert candidate_detail_response.status_code == 200
    assert candidate_detail_response.json()["status_history"][-1]["new_status"] == "shortlisted"

    withdraw_response = client.post(
        f"/candidate/job-applications/{job_application['id']}/withdraw",
        json={"expectedVersion": reviewed_application["version"]},
        headers=candidate_headers,
    )
    assert withdraw_response.status_code == 200
    assert withdraw_response.json()["status"] == "withdrawn"
    assert published_job["version"] == job["version"] + 1


def test_role_guards_for_candidate_and_hr_endpoints(client):
    candidate_headers = register_and_login(
        client,
        email="guard-candidate@example.edu",
        role="candidate",
        full_name="Guard Candidate",
    )
    hr_headers = register_and_login(
        client,
        email="guard-hr@example.edu",
        role="hr",
        full_name="Guard HR",
    )

    company_attempt = client.post(
        "/companies",
        json={"name": "Nope Co"},
        headers=candidate_headers,
    )
    assert company_attempt.status_code == 403

    tracker_attempt = client.post(
        "/applications",
        json={
            "company_name": "Blocked Co",
            "position_title": "Blocked Role",
            "job_description": "Should be candidate only.",
            "application_status": "Saved",
            "deadline": None,
            "notes": None,
        },
        headers=hr_headers,
    )
    assert tracker_attempt.status_code == 403


def test_job_board_returns_all_published_jobs_without_filters(client):
    hr_headers = register_and_login(
        client,
        email="jobs-all-hr@example.edu",
        role="hr",
        full_name="Jobs All HR",
    )

    company_response = client.post(
        "/companies",
        json={
            "name": "Filter Labs",
            "description": "Testing job filters.",
            "website": "https://filterlabs.example",
            "industry": "Technology",
            "location": "Bangkok",
            "logo_url": None,
        },
        headers=hr_headers,
    )
    assert company_response.status_code == 201

    first_job = client.post(
        "/hr/jobs",
        json={
            "title": "Cloud Engineer",
            "description": "AWS focused role.",
            "requirements": "Cloud basics",
            "responsibilities": "Support cloud team",
            "location": "Bangkok",
            "employment_type": "early_career",
            "work_mode": "hybrid",
            "salary_min": 0,
            "salary_max": 0,
            "deadline": "2026-12-31",
            "status": "published",
        },
        headers=hr_headers,
    )
    assert first_job.status_code == 201

    second_job = client.post(
        "/hr/jobs",
        json={
            "title": "Frontend Engineer",
            "description": "React focused role.",
            "requirements": "React basics",
            "responsibilities": "Support frontend team",
            "location": "Ho Chi Minh City",
            "employment_type": "early_career",
            "work_mode": "remote",
            "salary_min": 0,
            "salary_max": 0,
            "deadline": "2026-12-31",
            "status": "published",
        },
        headers=hr_headers,
    )
    assert second_job.status_code == 201

    draft_job = client.post(
        "/hr/jobs",
        json={
            "title": "Hidden Draft",
            "description": "Should not appear.",
            "requirements": "Confidential",
            "responsibilities": "Confidential",
            "location": "Bangkok",
            "employment_type": "full_time",
            "work_mode": "onsite",
            "salary_min": 0,
            "salary_max": 0,
            "deadline": "2026-12-31",
            "status": "draft",
        },
        headers=hr_headers,
    )
    assert draft_job.status_code == 201

    response = client.get("/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 2
    assert {job["title"] for job in jobs} == {"Cloud Engineer", "Frontend Engineer"}


def test_job_board_filters_support_blank_and_selected_values(client):
    hr_headers = register_and_login(
        client,
        email="jobs-filter-hr@example.edu",
        role="hr",
        full_name="Jobs Filter HR",
    )

    company_response = client.post(
        "/companies",
        json={
            "name": "Filter Matrix",
            "description": "Filter matrix jobs.",
            "website": "https://filtermatrix.example",
            "industry": "Technology",
            "location": "Singapore",
            "logo_url": None,
        },
        headers=hr_headers,
    )
    assert company_response.status_code == 201

    payloads = [
        {
            "title": "Early Career Hybrid",
            "description": "Early-career hybrid role.",
            "requirements": "Python",
            "responsibilities": "Build APIs",
            "location": "Singapore",
            "employment_type": "early_career",
            "work_mode": "hybrid",
        },
        {
            "title": "Early Career Remote",
            "description": "Early-career remote role.",
            "requirements": "React",
            "responsibilities": "Build UI",
            "location": "Singapore",
            "employment_type": "early_career",
            "work_mode": "remote",
        },
        {
            "title": "Full Time Onsite",
            "description": "Full-time onsite role.",
            "requirements": "SQL",
            "responsibilities": "Maintain systems",
            "location": "Singapore",
            "employment_type": "full_time",
            "work_mode": "onsite",
        },
    ]

    for payload in payloads:
        response = client.post(
            "/hr/jobs",
            json={
                **payload,
                "salary_min": 0,
                "salary_max": 0,
                "deadline": "2026-12-31",
                "status": "published",
            },
            headers=hr_headers,
        )
        assert response.status_code == 201

    early_career_jobs_response = client.get(
        "/jobs",
        params={"work_mode": "", "employment_type": "early_career"},
    )
    assert early_career_jobs_response.status_code == 200
    early_career_jobs = early_career_jobs_response.json()
    assert len(early_career_jobs) == 2
    assert {job["title"] for job in early_career_jobs} == {"Early Career Hybrid", "Early Career Remote"}

    hybrid_response = client.get(
        "/jobs",
        params={"work_mode": "hybrid", "employment_type": "early_career"},
    )
    assert hybrid_response.status_code == 200
    hybrid_jobs = hybrid_response.json()
    assert len(hybrid_jobs) == 1
    assert hybrid_jobs[0]["title"] == "Early Career Hybrid"
