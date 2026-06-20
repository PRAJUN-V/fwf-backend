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


def _setup_two_player_room(client: TestClient, admin_token: str):
    host_token, host_id = _make_player(client, admin_token)
    guest_token, guest_id = _make_player(client, admin_token)
    name = f"room_{uuid.uuid4().hex[:8]}"
    room = client.post(
        "/rooms",
        headers=auth_header(host_token),
        json={"name": name, "game_type": "snakes_and_ladders", "max_players": 2},
    ).json()
    client.post(f"/rooms/{room['id']}/join", headers=auth_header(guest_token))
    return room["id"], (host_token, host_id), (guest_token, guest_id)


def test_full_game_reaches_winner(client: TestClient, admin_token: str):
    room_id, (host_token, host_id), (guest_token, guest_id) = _setup_two_player_room(
        client, admin_token
    )

    with client.websocket_connect(
        f"/ws/rooms/{room_id}?token={host_token}"
    ) as ws_host, client.websocket_connect(
        f"/ws/rooms/{room_id}?token={guest_token}"
    ) as ws_guest:
        sockets = {host_id: ws_host, guest_id: ws_guest}

        # Drain host setup broadcasts (initial + host-connect + guest-connect).
        for _ in range(3):
            ws_host.receive_json()

        def read_host_state():
            msg = ws_host.receive_json()
            while msg.get("type") != "state" or msg.get("game") is None:
                msg = ws_host.receive_json()
            return msg["game"]

        ws_host.send_json({"action": "start"})
        game = read_host_state()
        assert game["status"] == "in_progress"

        winner = None
        turn = game["current_turn_user_id"]
        for _ in range(2000):
            sockets[turn].send_json({"action": "roll"})
            game = read_host_state()
            if game["winner_id"] is not None:
                winner = game["winner_id"]
                break
            turn = game["current_turn_user_id"]

        assert winner in (host_id, guest_id)


def test_roll_out_of_turn_is_rejected(client: TestClient, admin_token: str):
    room_id, (host_token, host_id), (guest_token, guest_id) = _setup_two_player_room(
        client, admin_token
    )

    with client.websocket_connect(
        f"/ws/rooms/{room_id}?token={host_token}"
    ) as ws_host, client.websocket_connect(
        f"/ws/rooms/{room_id}?token={guest_token}"
    ) as ws_guest:
        for _ in range(3):
            ws_host.receive_json()
        for _ in range(2):
            ws_guest.receive_json()

        ws_host.send_json({"action": "start"})
        # Host starts; first turn belongs to the host (seat 0).
        state = ws_host.receive_json()
        while state.get("type") != "state" or state.get("game") is None:
            state = ws_host.receive_json()
        assert state["game"]["current_turn_user_id"] == host_id

        # Guest tries to roll out of turn -> error message.
        ws_guest.send_json({"action": "roll"})
        msg = ws_guest.receive_json()
        while msg.get("type") not in ("error",):
            msg = ws_guest.receive_json()
        assert "turn" in msg["detail"].lower()


def test_non_host_cannot_start(client: TestClient, admin_token: str):
    room_id, (host_token, host_id), (guest_token, guest_id) = _setup_two_player_room(
        client, admin_token
    )

    with client.websocket_connect(
        f"/ws/rooms/{room_id}?token={guest_token}"
    ) as ws_guest:
        ws_guest.receive_json()
        ws_guest.send_json({"action": "start"})
        msg = ws_guest.receive_json()
        while msg.get("type") != "error":
            msg = ws_guest.receive_json()
        assert "host" in msg["detail"].lower()
