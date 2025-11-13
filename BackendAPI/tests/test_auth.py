from fastapi import status


def test_register_user_success(client):
    payload = {"email": "newuser@example.com", "password": "StrongPass1!"}
    r = client.post("/auth/register", json=payload)
    assert r.status_code == status.HTTP_200_OK, r.text
    data = r.json()
    assert data["email"] == payload["email"]
    assert "id" in data and isinstance(data["id"], int)


def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "StrongPass1!"}
    r1 = client.post("/auth/register", json=payload)
    assert r1.status_code in (200, 400)
    r2 = client.post("/auth/register", json=payload)
    assert r2.status_code == 400
    assert r2.json()["detail"] == "Email already registered"


def test_login_success_and_token_allows_me_endpoint(client):
    email, password = "alice@example.com", "Passw0rd!"
    # register
    client.post("/auth/register", json={"email": email, "password": password})
    # login
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body and isinstance(body["access_token"], str)
    assert body.get("token_type") == "bearer"

    # call /me with bearer token
    token = body["access_token"]
    mr = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert mr.status_code == 200, mr.text
    me = mr.json()
    assert me["email"] == email
    assert "id" in me


def test_login_invalid_credentials(client):
    # not registered user
    r1 = client.post("/auth/login", json={"email": "nouser@example.com", "password": "SomePass1!"})
    assert r1.status_code == 401
    assert r1.json()["detail"] == "Invalid email or password"

    # wrong password path
    client.post("/auth/register", json={"email": "bob@example.com", "password": "CorrectPass1!"})
    r2 = client.post("/auth/login", json={"email": "bob@example.com", "password": "WrongPass1!"})
    assert r2.status_code == 401
    assert r2.json()["detail"] == "Invalid email or password"
