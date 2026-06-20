import uuid

from fastapi.testclient import TestClient

from tests.conftest import auth_header


def _unique(prefix: str = "user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _create_user(client: TestClient, token: str, **overrides):
    name = overrides.get("username", _unique())
    payload = {
        "username": name,
        "email": overrides.get("email", f"{name}@example.com"),
        "password": overrides.get("password", "1234"),
        "is_admin": overrides.get("is_admin", False),
    }
    return client.post("/users", headers=auth_header(token), json=payload)


def test_admin_can_create_user(client: TestClient, admin_token: str):
    res = _create_user(client, admin_token)
    assert res.status_code == 201, res.text
    assert res.json()["is_admin"] is False


def test_duplicate_username_conflicts(client: TestClient, admin_token: str):
    name = _unique()
    assert _create_user(client, admin_token, username=name).status_code == 201
    dup = _create_user(client, admin_token, username=name)
    assert dup.status_code == 409


def test_non_admin_cannot_list_users(client: TestClient, admin_token: str):
    name = _unique("player")
    _create_user(client, admin_token, username=name, password="1234")
    token = client.post(
        "/auth/login", json={"username": name, "password": "1234"}
    ).json()["access_token"]

    res = client.get("/users", headers=auth_header(token))
    assert res.status_code == 403


def test_admin_can_update_user(client: TestClient, admin_token: str):
    created = _create_user(client, admin_token).json()
    new_email = f"{_unique()}@example.com"
    res = client.patch(
        f"/users/{created['id']}",
        headers=auth_header(admin_token),
        json={"email": new_email, "is_admin": True},
    )
    assert res.status_code == 200
    assert res.json()["email"] == new_email
    assert res.json()["is_admin"] is True


def test_admin_cannot_remove_own_privilege(client: TestClient, admin_token: str):
    me = client.get("/auth/me", headers=auth_header(admin_token)).json()
    res = client.patch(
        f"/users/{me['id']}",
        headers=auth_header(admin_token),
        json={"is_admin": False},
    )
    assert res.status_code == 400


def test_updated_password_allows_login(client: TestClient, admin_token: str):
    name = _unique("player")
    created = _create_user(client, admin_token, username=name, password="1234").json()
    client.patch(
        f"/users/{created['id']}",
        headers=auth_header(admin_token),
        json={"password": "newpass"},
    )
    assert (
        client.post("/auth/login", json={"username": name, "password": "newpass"}).status_code
        == 200
    )
