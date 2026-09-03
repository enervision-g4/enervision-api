from app.security import hash_password


def test_login_success(client, monkeypatch):
    monkeypatch.setattr("app.security.settings.api_username", "admin")
    monkeypatch.setattr(
        "app.security.settings.api_password_hash", hash_password("correct_password")
    )

    response = client.post(
        "/auth/login",
        data={"username": "admin", "password": "correct_password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password(client, monkeypatch):
    monkeypatch.setattr("app.security.settings.api_username", "admin")
    monkeypatch.setattr(
        "app.security.settings.api_password_hash", hash_password("correct_password")
    )

    response = client.post(
        "/auth/login",
        data={"username": "admin", "password": "wrong_password"},
    )

    assert response.status_code == 401


def test_login_unknown_username(client, monkeypatch):
    monkeypatch.setattr("app.security.settings.api_username", "admin")
    monkeypatch.setattr(
        "app.security.settings.api_password_hash", hash_password("correct_password")
    )

    response = client.post(
        "/auth/login",
        data={"username": "ghost", "password": "correct_password"},
    )

    assert response.status_code == 401


def test_protected_route_without_token_is_rejected(client):
    response = client.get("/api/v1/sites")

    assert response.status_code == 401


def test_protected_route_with_invalid_token_is_rejected(client):
    response = client.get(
        "/api/v1/sites", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401
