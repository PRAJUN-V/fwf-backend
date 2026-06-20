"""WebSocket endpoint for live room gameplay (Snake & Ladder + Number Prediction).

Clients connect to /ws/rooms/{room_id}?token=JWT. The DB is the source of
truth; every action mutates the DB and the new state is broadcast.

State is built per-viewer so private data (e.g. number-prediction secrets) is
never sent to other players.
"""

import asyncio
from collections import defaultdict
from collections.abc import Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api.deps import get_user_from_token
from app.core.database import SessionLocal
from app.models.room import GameType, Room
from app.services import hand_cricket_service, number_service, room_service
from app.services.room_service import RoomError

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[int, dict[WebSocket, int]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def connect(self, room_id: int, websocket: WebSocket, user_id: int) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms[room_id][websocket] = user_id

    async def disconnect(self, room_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            self._rooms[room_id].pop(websocket, None)
            if not self._rooms[room_id]:
                self._rooms.pop(room_id, None)

    async def broadcast(self, room_id: int, build: Callable[[int], dict]) -> None:
        """Send each connection a payload built for its own user."""
        async with self._lock:
            items = list(self._rooms.get(room_id, {}).items())
        for connection, user_id in items:
            try:
                await connection.send_json(build(user_id))
            except Exception:
                pass


manager = ConnectionManager()


def _build_state(db: Session, room: Room, viewer_id: int) -> dict:
    payload: dict = {
        "type": "state",
        "room": room_service.serialize_room(db, room).model_dump(mode="json"),
        "game": None,
        "number": None,
        "hand_cricket": None,
    }
    if room.game_type == GameType.snakes_and_ladders:
        if room.game is not None:
            payload["game"] = room_service.serialize_game_state(db, room).model_dump(
                mode="json"
            )
    elif room.game_type == GameType.number_prediction:
        payload["number"] = number_service.serialize_state(db, room, viewer_id)
    elif room.game_type == GameType.hand_cricket:
        payload["hand_cricket"] = hand_cricket_service.serialize_state(
            db, room, viewer_id
        )
    return payload


def _handle_action(db: Session, room: Room, user_id: int, data: dict) -> None:
    action = data.get("action")

    if room.game_type == GameType.snakes_and_ladders:
        if action == "start":
            room_service.start_game(db, room=room, user_id=user_id)
        elif action == "roll":
            room_service.roll_dice(db, room=room, user_id=user_id)
        elif action == "sync":
            return
        else:
            raise RoomError(f"Unknown action: {action}")
    elif room.game_type == GameType.number_prediction:
        if action == "set_secret":
            number_service.set_secret(db, room=room, user_id=user_id, value=data.get("value"))
        elif action == "start":
            number_service.start_game(db, room=room, user_id=user_id)
        elif action == "guess":
            number_service.make_guess(db, room=room, user_id=user_id, value=data.get("value"))
        elif action == "sync":
            return
        else:
            raise RoomError(f"Unknown action: {action}")
    elif room.game_type == GameType.hand_cricket:
        if action == "start":
            hand_cricket_service.start_game(db, room=room, user_id=user_id)
        elif action == "begin_innings_2":
            hand_cricket_service.begin_innings_two(db, room=room, user_id=user_id)
        elif action == "reveal":
            hand_cricket_service.reveal_fingers(
                db, room=room, user_id=user_id, value=data.get("value")
            )
        elif action == "sync":
            return
        else:
            raise RoomError(f"Unknown action: {action}")
    else:
        raise RoomError("Unsupported game type")


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: int, token: str | None = None) -> None:
    db: Session = SessionLocal()
    try:
        if not token:
            await websocket.close(code=4401)
            return
        try:
            user = get_user_from_token(token, db)
        except Exception:
            await websocket.close(code=4401)
            return

        room = db.get(Room, room_id)
        if room is None:
            await websocket.close(code=4404)
            return

        # Private rooms: only members (host + joined players) may connect.
        if not room_service.is_member(room, user.id):
            await websocket.close(code=4403)
            return

        await manager.connect(room_id, websocket, user.id)
        await websocket.send_json(_build_state(db, room, user.id))
        await manager.broadcast(room_id, lambda uid: _build_state(db, room, uid))

        while True:
            data = await websocket.receive_json()

            db.expire_all()
            room = db.get(Room, room_id)
            if room is None:
                await websocket.send_json({"type": "error", "detail": "Room no longer exists"})
                break

            try:
                handled = data.get("action")
                _handle_action(db, room, user.id, data)
                if handled == "sync":
                    await websocket.send_json(_build_state(db, room, user.id))
                    continue
            except RoomError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
                continue

            room = db.get(Room, room_id)
            await manager.broadcast(room_id, lambda uid: _build_state(db, room, uid))

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(room_id, websocket)
        db.close()
