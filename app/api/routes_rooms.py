from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.room import Room
from app.models.user import User
from app.schemas.room import RoomCreate, RoomJoinByCode, RoomOut
from app.services import room_service
from app.services.room_service import RoomError, RoomNotFound

router = APIRouter(prefix="/rooms", tags=["rooms"])


def _get_room_or_404(db: Session, room_id: int) -> Room:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return room


@router.get("", response_model=list[RoomOut])
def list_rooms(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[RoomOut]:
    # Private rooms: a user only sees rooms they are part of.
    rooms = room_service.list_user_rooms(db, current_user.id)
    return [room_service.serialize_room(db, room) for room in rooms]


@router.post("", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(
    payload: RoomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoomOut:
    try:
        room = room_service.create_room(
            db,
            name=payload.name,
            game_type=payload.game_type,
            max_players=payload.max_players,
            host_id=current_user.id,
        )
    except RoomError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return room_service.serialize_room(db, room)


@router.post("/join", response_model=RoomOut)
def join_by_code(
    payload: RoomJoinByCode,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoomOut:
    try:
        room = room_service.get_room_by_code(db, payload.code)
        room = room_service.join_room(db, room=room, user_id=current_user.id)
    except RoomNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RoomError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return room_service.serialize_room(db, room)


@router.get("/{room_id}", response_model=RoomOut)
def get_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoomOut:
    room = _get_room_or_404(db, room_id)
    if not room_service.is_member(room, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this room")
    return room_service.serialize_room(db, room)


@router.post("/{room_id}/leave", status_code=status.HTTP_200_OK)
def leave_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    room = _get_room_or_404(db, room_id)
    result = room_service.leave_room(db, room=room, user_id=current_user.id)
    if result is None:
        return {"deleted": True}
    return {"deleted": False}
