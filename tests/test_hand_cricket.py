import uuid

from fastapi.testclient import TestClient

from tests.conftest import auth_header


def _make_player(client: TestClient, admin_token: str) -> tuple[str, int]:
    name = f"p_{uuid.uuid4().hex[:8]}"
    client.post(
        "/users",
        headers=auth_header(admin_token),
        json={"username": name, "email": f"{name}@example.com", "password": "1234"},
    )
    token = client.post(
        "/auth/login", json={"username": name, "password": "1234"}
    ).json()["access_token"]
    uid = client.get("/auth/me", headers=auth_header(token)).json()["id"]
    return token, uid


def _setup_room(client: TestClient, admin_token: str):
    host_token, host_id = _make_player(client, admin_token)
    guest_token, guest_id = _make_player(client, admin_token)
    name = f"hc_{uuid.uuid4().hex[:8]}"
    room = client.post(
        "/rooms",
        headers=auth_header(host_token),
        json={"name": name, "game_type": "hand_cricket", "max_players": 2},
    ).json()
    client.post("/rooms/join", headers=auth_header(guest_token), json={"code": room["code"]})
    return room, (host_token, host_id), (guest_token, guest_id)


def _drain(ws, count: int):
    for _ in range(count):
        ws.receive_json()


def _next_state(ws):
    msg = ws.receive_json()
    while msg.get("type") != "state":
        msg = ws.receive_json()
    return msg["hand_cricket"]


def test_create_forces_two_players(client: TestClient, admin_token: str):
    host_token, _ = _make_player(client, admin_token)
    room = client.post(
        "/rooms",
        headers=auth_header(host_token),
        json={"name": "hc", "game_type": "hand_cricket", "max_players": 4},
    ).json()
    assert room["max_players"] == 2


def test_wicket_ends_innings(client: TestClient, admin_token: str):
    room, (host_token, host_id), (guest_token, guest_id) = _setup_room(
        client, admin_token
    )
    room_id = room["id"]

    with client.websocket_connect(
        f"/ws/rooms/{room_id}?token={host_token}"
    ) as ws_host, client.websocket_connect(
        f"/ws/rooms/{room_id}?token={guest_token}"
    ) as ws_guest:
        _drain(ws_host, 3)
        _drain(ws_guest, 2)

        ws_host.send_json({"action": "start"})
        st = _next_state(ws_host)
        _next_state(ws_guest)
        assert st["status"] == "in_progress"
        assert st["your_role"] == "bat"

        # Both show 4 → wicket, innings break
        ws_host.send_json({"action": "reveal", "value": 4})
        _next_state(ws_host)
        _next_state(ws_guest)
        ws_guest.send_json({"action": "reveal", "value": 4})
        st = _next_state(ws_host)
        assert st["last_ball"]["is_wicket"] is True
        assert st["status"] == "innings_break"


def test_full_match_with_runs(client: TestClient, admin_token: str):
    room, (host_token, host_id), (guest_token, guest_id) = _setup_room(
        client, admin_token
    )
    room_id = room["id"]

    with client.websocket_connect(
        f"/ws/rooms/{room_id}?token={host_token}"
    ) as ws_host, client.websocket_connect(
        f"/ws/rooms/{room_id}?token={guest_token}"
    ) as ws_guest:
        _drain(ws_host, 3)
        _drain(ws_guest, 2)
        ws_host.send_json({"action": "start"})
        _next_state(ws_host)
        _next_state(ws_guest)

        # Innings 1: host bats — 3 runs (host=3, guest=5 different)
        ws_host.send_json({"action": "reveal", "value": 3})
        _next_state(ws_host)
        _next_state(ws_guest)
        ws_guest.send_json({"action": "reveal", "value": 5})
        st = _next_state(ws_host)
        assert st["player1_runs"] == 3
        assert st["ball_number"] == 2

        # Bowl 5 more balls without wicket (always different)
        pairs = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6)]
        for bat, bowl in pairs:
            ws_host.send_json({"action": "reveal", "value": bat})
            _next_state(ws_host)
            _next_state(ws_guest)
            ws_guest.send_json({"action": "reveal", "value": bowl})
            st = _next_state(ws_host)
            _next_state(ws_guest)

        assert st["status"] == "innings_break"
        assert st["player1_runs"] == 3 + 1 + 2 + 3 + 4 + 5  # 18

        ws_host.send_json({"action": "begin_innings_2"})
        st = _next_state(ws_host)
        _next_state(ws_guest)
        assert st["status"] == "in_progress"
        assert st["innings"] == 2

        # Innings 2: guest bats — one ball with 6 runs then wicket on ball 2
        ws_guest.send_json({"action": "reveal", "value": 6})
        _next_state(ws_host)
        _next_state(ws_guest)
        ws_host.send_json({"action": "reveal", "value": 1})
        st = _next_state(ws_host)
        assert st["player2_runs"] == 6

        ws_guest.send_json({"action": "reveal", "value": 2})
        _next_state(ws_host)
        _next_state(ws_guest)
        ws_host.send_json({"action": "reveal", "value": 2})
        st = _next_state(ws_host)
        assert st["status"] == "finished"
        assert st["winner_id"] == host_id
