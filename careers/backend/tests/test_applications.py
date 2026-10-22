def auth_headers(client):
    client.post(
        "/auth/register",
        json={
            "email": "crud@example.edu",
            "full_name": "CRUD Tester",
            "password": "Strong!Pass123",
        },
    )
    response = client.post(
        "/auth/login",
        json={"email": "crud@example.edu", "password": "Strong!Pass123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_application_crud(client):
    headers = auth_headers(client)
    payload = {
        "company_name": "Amazon",
        "position_title": "Cloud Intern",
        "job_description": "Python FastAPI AWS S3 Docker role.",
        "application_status": "Saved",
        "deadline": "2026-07-01",
        "notes": "Apply soon.",
    }
    create_response = client.post("/applications", json=payload, headers=headers)
    assert create_response.status_code == 201
    application_id = create_response.json()["id"]

    list_response = client.get("/applications", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    update_response = client.put(
        f"/applications/{application_id}",
        json={"application_status": "Applied", "notes": "Submitted."},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["application_status"] == "Applied"

    delete_response = client.delete(f"/applications/{application_id}", headers=headers)
    assert delete_response.status_code == 200
    assert client.get("/applications", headers=headers).json() == []
