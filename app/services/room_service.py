"""Business logic for rooms and the Snake & Ladder game lifecycle.

Centralized so both the REST routes and the WebSocket handler share one
source of truth. Functions here operate on a SQLAlchemy session and commit
their own changes.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.games import snakes_and_ladders as snl
from app.models.game import Game, GamePlayerState, GameStatus
from app.models.room import Room, RoomStatus
from app.models.room_player import RoomPlayer
from app.schemas.game import GamePlayerStateOut, GameStateOut
from app.schemas.room import RoomOut, RoomPlayerOut


class RoomError(Exception):
    """Raised for invalid room/game operations (maps to HTTP 400)."""


def _next_color(seat_order: int) -> str:
    colors = snl.PLAYER_COLORS
    return colors[seat_order % len(colors)]


def serialize_room(db: Session, room: Room) -> RoomOut:
    players = sorted(room.players, key=lambda p: p.seat_order)
    return RoomOut(
        id=room.id,
        name=room.name,
        game_type=room.game_type,
        max_players=room.max_players,
        status=room.status,
        host_id=room.host_id,
        created_at=room.created_at,
        player_count=len(players),
        players=[
            RoomPlayerOut(
                user_id=p.user_id,
                username=p.user.username,
                seat_order=p.seat_order,
                color=p.color,
            )
            for p in players
        ],
    )


def serialize_game_state(db: Session, room: Room) -> GameStateOut:
    game = room.game
    if game is None:
        raise RoomError("Game has not started")

    color_by_user = {p.user_id: p.color for p in room.players}
    username_by_user = {p.user_id: p.user.username for p in room.players}

    states = sorted(game.player_states, key=lambda s: s.seat_order)
    return GameStateOut(
        room_id=room.id,
        game_id=game.id,
        status=game.status,
        current_turn_user_id=game.current_turn_user_id,
        last_dice=game.last_dice,
        winner_id=game.winner_id,
        players=[
            GamePlayerStateOut(
                user_id=s.user_id,
                username=username_by_user.get(s.user_id, "?"),
                color=color_by_user.get(s.user_id, "red"),
                seat_order=s.seat_order,
                position=s.position,
            )
            for s in states
        ],
    )


def list_open_rooms(db: Session) -> list[Room]:
    stmt = select(Room).where(Room.status != RoomStatus.finished).order_by(Room.created_at.desc())
    return list(db.scalars(stmt))


def create_room(
    db: Session, *, name: str, game_type, max_players: int, host_id: int
) -> Room:
    existing = db.scalar(
        select(Room).where(Room.name == name, Room.status != RoomStatus.finished)
    )
    if existing is not None:
        raise RoomError("A room with this name already exists")

    room = Room(
        name=name,
        game_type=game_type,
        max_players=max_players,
        host_id=host_id,
        status=RoomStatus.waiting,
    )
    db.add(room)
    db.flush()

    host_player = RoomPlayer(
        room_id=room.id, user_id=host_id, seat_order=0, color=_next_color(0)
    )
    db.add(host_player)
    db.commit()
    db.refresh(room)
    return room


def join_room(db: Session, *, room: Room, user_id: int) -> Room:
    if room.status != RoomStatus.waiting:
        raise RoomError("Game already started")

    already = next((p for p in room.players if p.user_id == user_id), None)
    if already is not None:
        return room

    if len(room.players) >= room.max_players:
        raise RoomError("Room is full")

    seat_order = len(room.players)
    db.add(
        RoomPlayer(
            room_id=room.id,
            user_id=user_id,
            seat_order=seat_order,
            color=_next_color(seat_order),
        )
    )
    db.commit()
    db.refresh(room)
    return room


def leave_room(db: Session, *, room: Room, user_id: int) -> Room | None:
    player = next((p for p in room.players if p.user_id == user_id), None)
    if player is None:
        return room

    db.delete(player)
    db.flush()
    db.refresh(room)

    remaining = sorted(room.players, key=lambda p: p.seat_order)
    if not remaining:
        db.delete(room)
        db.commit()
        return None

    # Reassign seats/colors and host if needed.
    for index, p in enumerate(remaining):
        p.seat_order = index
        p.color = _next_color(index)
    if room.host_id == user_id:
        room.host_id = remaining[0].user_id

    db.commit()
    db.refresh(room)
    return room


def start_game(db: Session, *, room: Room, user_id: int) -> Room:
    if room.host_id != user_id:
        raise RoomError("Only the host can start the game")
    if room.status != RoomStatus.waiting:
        raise RoomError("Game already started")
    if len(room.players) < 2:
        raise RoomError("Need at least 2 players to start")

    players = sorted(room.players, key=lambda p: p.seat_order)
    game = Game(
        room_id=room.id,
        status=GameStatus.in_progress,
        current_turn_user_id=players[0].user_id,
    )
    db.add(game)
    db.flush()

    for p in players:
        db.add(
            GamePlayerState(
                game_id=game.id, user_id=p.user_id, seat_order=p.seat_order, position=0
            )
        )

    room.status = RoomStatus.playing
    db.commit()
    db.refresh(room)
    return room


def roll_dice(db: Session, *, room: Room, user_id: int) -> Room:
    game = room.game
    if game is None or game.status != GameStatus.in_progress:
        raise RoomError("Game is not in progress")
    if game.current_turn_user_id != user_id:
        raise RoomError("It is not your turn")

    states = sorted(game.player_states, key=lambda s: s.seat_order)
    current = next((s for s in states if s.user_id == user_id), None)
    if current is None:
        raise RoomError("You are not part of this game")

    dice = snl.roll_die()
    new_position, _ = snl.resolve_move(current.position, dice)
    current.position = new_position
    game.last_dice = dice

    if snl.is_winning_position(new_position):
        game.winner_id = user_id
        game.status = GameStatus.finished
        room.status = RoomStatus.finished
        game.current_turn_user_id = None
    else:
        order = [s.user_id for s in states]
        idx = order.index(user_id)
        game.current_turn_user_id = order[(idx + 1) % len(order)]

    db.commit()
    db.refresh(room)
    return room
