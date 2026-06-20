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


def _join_by_code(client: TestClient, token: str, code: str):
    return client.post("/rooms/join", headers=auth_header(token), json={"code": code})


def test_create_room_has_code_and_host(client: TestClient, admin_token: str):
    res = _create_room(client, admin_token)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["player_count"] == 1
    assert body["host_id"] is not None
    assert body["code"] and len(body["code"]) >= 4


def test_join_by_code(client: TestClient, admin_token: str):
    room = _create_room(client, admin_token).json()
    player = _make_player(client, admin_token)
    res = _join_by_code(client, player, room["code"])
    assert res.status_code == 200, res.text
    assert res.json()["player_count"] == 2
    assert res.json()["id"] == room["id"]


def test_join_with_unknown_code_404(client: TestClient, admin_token: str):
    player = _make_player(client, admin_token)
    res = _join_by_code(client, player, "ZZZZZZ")
    assert res.status_code == 404


def test_room_full_rejected(client: TestClient, admin_token: str):
    room = _create_room(client, admin_token, max_players=2).json()
    p1 = _make_player(client, admin_token)
    p2 = _make_player(client, admin_token)
    assert _join_by_code(client, p1, room["code"]).status_code == 200
    res = _join_by_code(client, p2, room["code"])
    assert res.status_code == 400
    assert "full" in res.json()["detail"].lower()


def test_list_only_shows_my_rooms(client: TestClient, admin_token: str):
    # Admin creates a room; a different player should not see it in their list.
    room = _create_room(client, admin_token).json()
    other = _make_player(client, admin_token)
    listed = client.get("/rooms", headers=auth_header(other)).json()
    assert all(r["id"] != room["id"] for r in listed)

    # After joining by code, it appears in their list.
    _join_by_code(client, other, room["code"])
    listed_after = client.get("/rooms", headers=auth_header(other)).json()
    assert any(r["id"] == room["id"] for r in listed_after)


def test_non_member_cannot_get_room(client: TestClient, admin_token: str):
    room = _create_room(client, admin_token).json()
    other = _make_player(client, admin_token)
    res = client.get(f"/rooms/{room['id']}", headers=auth_header(other))
    assert res.status_code == 403


def test_leave_room_removes_player(client: TestClient, admin_token: str):
    room = _create_room(client, admin_token).json()
    player = _make_player(client, admin_token)
    _join_by_code(client, player, room["code"])

    res = client.post(f"/rooms/{room['id']}/leave", headers=auth_header(player))
    assert res.status_code == 200
    after = client.get(f"/rooms/{room['id']}", headers=auth_header(admin_token)).json()
    assert after["player_count"] == 1
