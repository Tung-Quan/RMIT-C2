def test_register_login_and_get_current_user(client):
    register_response = client.post(
        "/auth/register",
        json={
            "email": "student@example.edu",
            "full_name": "Student User",
            "password": "Strong!Pass123",
        },
    )
    assert register_response.status_code == 201
    assert register_response.json()["email"] == "student@example.edu"

    login_response = client.post(
        "/auth/login",
        json={"email": "student@example.edu", "password": "Strong!Pass123"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["full_name"] == "Student User"


def test_swagger_oauth_form_login(client):
    client.post(
        "/auth/register",
        json={
            "email": "swagger@example.edu",
            "full_name": "Swagger User",
            "password": "Strong!Pass123",
        },
    )

    response = client.post(
        "/auth/login",
        data={"username": "swagger@example.edu", "password": "Strong!Pass123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
