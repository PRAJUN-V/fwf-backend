from fastapi.testclient import TestClient

from tests.conftest import auth_header


def test_health(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


def test_login_success(client: TestClient):
    res = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "admin"
    assert body["user"]["is_admin"] is True


def test_login_wrong_password(client: TestClient):
    res = client.post("/auth/login", json={"username": "admin", "password": "nope"})
    assert res.status_code == 401


def test_me_requires_token(client: TestClient):
    assert client.get("/auth/me").status_code == 401


def test_me_returns_current_user(client: TestClient, admin_token: str):
    res = client.get("/auth/me", headers=auth_header(admin_token))
    assert res.status_code == 200
    assert res.json()["username"] == "admin"
