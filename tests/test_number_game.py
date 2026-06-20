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
    name = f"np_{uuid.uuid4().hex[:8]}"
    room = client.post(
        "/rooms",
        headers=auth_header(host_token),
        json={"name": name, "game_type": "number_prediction", "max_players": 2},
    ).json()
    client.post("/rooms/join", headers=auth_header(guest_token), json={"code": room["code"]})
    return room, (host_token, host_id), (guest_token, guest_id)


def test_create_forces_two_players(client: TestClient, admin_token: str):
    host_token, _ = _make_player(client, admin_token)
    room = client.post(
        "/rooms",
        headers=auth_header(host_token),
        json={"name": "np", "game_type": "number_prediction", "max_players": 4},
    ).json()
    assert room["max_players"] == 2
    assert room["game_type"] == "number_prediction"


def _read_state(ws, viewer_drain: int):
    for _ in range(viewer_drain):
        ws.receive_json()


def test_full_number_game_flow(client: TestClient, admin_token: str):
    room, (host_token, host_id), (guest_token, guest_id) = _setup_room(client, admin_token)
    room_id = room["id"]

    with client.websocket_connect(
        f"/ws/rooms/{room_id}?token={host_token}"
    ) as ws_host, client.websocket_connect(
        f"/ws/rooms/{room_id}?token={guest_token}"
    ) as ws_guest:
        # Drain host setup broadcasts (initial + host-connect + guest-connect).
        for _ in range(3):
            ws_host.receive_json()
        for _ in range(2):
            ws_guest.receive_json()

        def host_state():
            msg = ws_host.receive_json()
            while msg.get("type") != "state":
                msg = ws_host.receive_json()
            return msg["number"]

        def guest_state():
            msg = ws_guest.receive_json()
            while msg.get("type") != "state":
                msg = ws_guest.receive_json()
            return msg["number"]

        # Set secrets: host=100, guest=500.
        ws_host.send_json({"action": "set_secret", "value": 100})
        host_state()
        guest_state()
        ws_guest.send_json({"action": "set_secret", "value": 500})
        st_host = host_state()
        guest_state()

        assert st_host["your_secret"] == 100
        assert st_host["you_ready"] is True
        # Host must not see the guest's secret yet.
        assert st_host["opponent_secret"] is None

        # Host starts.
        ws_host.send_json({"action": "start"})
        st = host_state()
        guest_state()
        assert st["status"] == "in_progress"
        assert st["current_turn_user_id"] == host_id

        # Host guesses the guest's number (500). First too low, then correct.
        ws_host.send_json({"action": "guess", "value": 300})
        st = host_state()
        guest_state()
        assert st["your_guesses"][-1] == {"value": 300, "result": "low"}
        # Turn passes to guest.
        assert st["current_turn_user_id"] == guest_id

        # Guest guesses host's number (100): 200 -> high.
        ws_guest.send_json({"action": "guess", "value": 200})
        host_state()
        gst = guest_state()
        assert gst["your_guesses"][-1] == {"value": 200, "result": "high"}

        # Host's turn again -> guess 500 correct -> host wins.
        ws_host.send_json({"action": "guess", "value": 500})
        st = host_state()
        gst = guest_state()
        assert st["winner_id"] == host_id
        assert st["status"] == "finished"
        # Both secrets revealed at the end.
        assert st["opponent_secret"] == 500
        assert gst["opponent_secret"] == 100


def test_cannot_start_without_secrets(client: TestClient, admin_token: str):
    room, (host_token, host_id), (guest_token, guest_id) = _setup_room(client, admin_token)
    room_id = room["id"]
    with client.websocket_connect(f"/ws/rooms/{room_id}?token={host_token}") as ws_host:
        ws_host.receive_json()
        ws_host.send_json({"action": "start"})
        msg = ws_host.receive_json()
        while msg.get("type") != "error":
            msg = ws_host.receive_json()
        assert "secret" in msg["detail"].lower()


def test_guess_out_of_turn_rejected(client: TestClient, admin_token: str):
    room, (host_token, host_id), (guest_token, guest_id) = _setup_room(client, admin_token)
    room_id = room["id"]
    with client.websocket_connect(
        f"/ws/rooms/{room_id}?token={host_token}"
    ) as ws_host, client.websocket_connect(
        f"/ws/rooms/{room_id}?token={guest_token}"
    ) as ws_guest:
        for _ in range(3):
            ws_host.receive_json()
        for _ in range(2):
            ws_guest.receive_json()

        ws_host.send_json({"action": "set_secret", "value": 10})
        ws_guest.send_json({"action": "set_secret", "value": 20})
        # drain
        for _ in range(2):
            ws_host.receive_json()
        ws_host.send_json({"action": "start"})
        # Guest (not their turn) tries to guess.
        ws_guest.send_json({"action": "guess", "value": 5})
        msg = ws_guest.receive_json()
        while msg.get("type") != "error":
            msg = ws_guest.receive_json()
        assert "turn" in msg["detail"].lower()
