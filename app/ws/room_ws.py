"""WebSocket endpoint for live room + Snake & Ladder gameplay.

Clients connect to /ws/rooms/{room_id}?token=JWT. The DB is the source of
truth; every action mutates the DB and the new state is broadcast to everyone
connected to the room.
"""

import asyncio
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api.deps import get_user_from_token
from app.core.database import SessionLocal
from app.models.room import Room
from app.services import room_service
from app.services.room_service import RoomError

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, room_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms[room_id].add(websocket)

    async def disconnect(self, room_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            self._rooms[room_id].discard(websocket)
            if not self._rooms[room_id]:
                self._rooms.pop(room_id, None)

    async def broadcast(self, room_id: int, message: dict) -> None:
        async with self._lock:
            connections = list(self._rooms.get(room_id, set()))
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


def _build_state(db: Session, room: Room) -> dict:
    payload: dict = {
        "type": "state",
        "room": room_service.serialize_room(db, room).model_dump(mode="json"),
        "game": None,
    }
    if room.game is not None:
        payload["game"] = room_service.serialize_game_state(db, room).model_dump(mode="json")
    return payload


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

        await manager.connect(room_id, websocket)
        await websocket.send_json(_build_state(db, room))
        await manager.broadcast(room_id, _build_state(db, room))

        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            db.expire_all()
            room = db.get(Room, room_id)
            if room is None:
                await websocket.send_json({"type": "error", "detail": "Room no longer exists"})
                break

            try:
                if action == "start":
                    room_service.start_game(db, room=room, user_id=user.id)
                elif action == "roll":
                    room_service.roll_dice(db, room=room, user_id=user.id)
                elif action == "sync":
                    pass
                else:
                    await websocket.send_json(
                        {"type": "error", "detail": f"Unknown action: {action}"}
                    )
                    continue
            except RoomError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
                continue

            room = db.get(Room, room_id)
            await manager.broadcast(room_id, _build_state(db, room))

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(room_id, websocket)
        db.close()
