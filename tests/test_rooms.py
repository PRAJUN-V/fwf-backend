import uuid

from fastapi.testclient import TestClient

from tests.conftest import auth_header


def _make_player(client: TestClient, admin_token: str) -> str:
    name = f"p_{uuid.uuid4().hex[:8]}"
    client.post(
        "/users",
        headers=auth_header(admin_token),
        json={"username": name, "email": f"{name}@example.com", "password": "1234"},
    )
    return client.post(
        "/auth/login", json={"username": name, "password": "1234"}
    ).json()["access_token"]


def _create_room(client: TestClient, token: str, max_players: int = 2):
    name = f"room_{uuid.uuid4().hex[:8]}"
    return client.post(
        "/rooms",
        headers=auth_header(token),
        json={"name": name, "game_type": "snakes_and_ladders", "max_players": max_players},
    )


def test_create_room_adds_host(client: TestClient, admin_token: str):
    res = _create_room(client, admin_token)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["player_count"] == 1
    assert body["host_id"] is not None


def test_join_room(client: TestClient, admin_token: str):
    room = _create_room(client, admin_token).json()
    player = _make_player(client, admin_token)
    res = client.post(f"/rooms/{room['id']}/join", headers=auth_header(player))
    assert res.status_code == 200
    assert res.json()["player_count"] == 2


def test_room_full_rejected(client: TestClient, admin_token: str):
    room = _create_room(client, admin_token, max_players=2).json()
    p1 = _make_player(client, admin_token)
    p2 = _make_player(client, admin_token)
    assert client.post(f"/rooms/{room['id']}/join", headers=auth_header(p1)).status_code == 200
    res = client.post(f"/rooms/{room['id']}/join", headers=auth_header(p2))
    assert res.status_code == 400
    assert "full" in res.json()["detail"].lower()


def test_leave_room_removes_player(client: TestClient, admin_token: str):
    room = _create_room(client, admin_token).json()
    player = _make_player(client, admin_token)
    client.post(f"/rooms/{room['id']}/join", headers=auth_header(player))

    res = client.post(f"/rooms/{room['id']}/leave", headers=auth_header(player))
    assert res.status_code == 200
    after = client.get(f"/rooms/{room['id']}", headers=auth_header(admin_token)).json()
    assert after["player_count"] == 1


def test_duplicate_room_name_rejected(client: TestClient, admin_token: str):
    name = f"room_{uuid.uuid4().hex[:8]}"
    body = {"name": name, "game_type": "snakes_and_ladders", "max_players": 2}
    first = client.post("/rooms", headers=auth_header(admin_token), json=body)
    assert first.status_code == 201
    second = client.post("/rooms", headers=auth_header(admin_token), json=body)
    assert second.status_code == 400
