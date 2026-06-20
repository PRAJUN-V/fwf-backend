"""Business logic for the Number Prediction game.

Two players each pick a secret number (0-1000). They then take turns guessing
the opponent's number; after each guess they're told whether it was too low or
too high. The first to guess the opponent's number exactly wins.

Secrets are private: they are never included in broadcasts. State is serialized
per viewer (see ``serialize_state``), so each player only sees their own secret.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.number_game import GuessResult, NumberGame, NumberGameStatus, NumberGuess
from app.models.room import Room, RoomStatus
from app.services.room_service import RoomError

MIN_NUMBER = 0
MAX_NUMBER = 1000


def _players(room: Room):
    return sorted(room.players, key=lambda p: p.seat_order)


def _opponent(room: Room, user_id: int):
    return next((p for p in room.players if p.user_id != user_id), None)


def set_secret(db: Session, *, room: Room, user_id: int, value: int) -> Room:
    if room.status != RoomStatus.waiting:
        raise RoomError("The game has already started")
    if not isinstance(value, int):
        raise RoomError("Pick a whole number")
    if value < MIN_NUMBER or value > MAX_NUMBER:
        raise RoomError(f"Pick a number between {MIN_NUMBER} and {MAX_NUMBER}")

    player = next((p for p in room.players if p.user_id == user_id), None)
    if player is None:
        raise RoomError("You are not part of this room")

    player.secret_number = value
    db.commit()
    db.refresh(room)
    return room


def start_game(db: Session, *, room: Room, user_id: int) -> Room:
    if room.host_id != user_id:
        raise RoomError("Only the host can start the game")
    if room.status != RoomStatus.waiting:
        raise RoomError("The game has already started")

    players = _players(room)
    if len(players) != 2:
        raise RoomError("Number prediction needs exactly 2 players")
    if any(p.secret_number is None for p in players):
        raise RoomError("Both players must set their secret number first")

    game = NumberGame(
        room_id=room.id,
        status=NumberGameStatus.in_progress,
        current_turn_user_id=players[0].user_id,
    )
    db.add(game)
    room.status = RoomStatus.playing
    db.commit()
    db.refresh(room)
    return room


def make_guess(db: Session, *, room: Room, user_id: int, value: int) -> Room:
    game = room.number_game
    if game is None or game.status != NumberGameStatus.in_progress:
        raise RoomError("The game is not in progress")
    if game.current_turn_user_id != user_id:
        raise RoomError("It is not your turn")
    if not isinstance(value, int) or value < MIN_NUMBER or value > MAX_NUMBER:
        raise RoomError(f"Guess a number between {MIN_NUMBER} and {MAX_NUMBER}")

    opponent = _opponent(room, user_id)
    if opponent is None or opponent.secret_number is None:
        raise RoomError("Opponent is not ready")

    secret = opponent.secret_number
    if value < secret:
        result = GuessResult.low
    elif value > secret:
        result = GuessResult.high
    else:
        result = GuessResult.correct

    db.add(
        NumberGuess(
            game_id=game.id,
            guesser_id=user_id,
            target_id=opponent.user_id,
            value=value,
            result=result,
        )
    )

    if result == GuessResult.correct:
        game.winner_id = user_id
        game.status = NumberGameStatus.finished
        game.current_turn_user_id = None
        room.status = RoomStatus.finished
    else:
        game.current_turn_user_id = opponent.user_id

    db.commit()
    db.refresh(room)
    return room


def serialize_state(db: Session, room: Room, viewer_id: int) -> dict:
    """Build the game state from a single viewer's perspective (private)."""
    players = _players(room)
    you = next((p for p in players if p.user_id == viewer_id), None)
    opponent = _opponent(room, viewer_id)
    game = room.number_game

    finished = game is not None and game.status == NumberGameStatus.finished

    if game is None:
        status = "setup"
        current_turn = None
        winner_id = None
    else:
        status = game.status.value
        current_turn = game.current_turn_user_id
        winner_id = game.winner_id

    your_guesses: list[dict] = []
    opponent_guesses: list[dict] = []
    if game is not None:
        guesses = db.scalars(
            select(NumberGuess)
            .where(NumberGuess.game_id == game.id)
            .order_by(NumberGuess.id)
        )
        for g in guesses:
            entry = {"value": g.value, "result": g.result.value}
            if g.guesser_id == viewer_id:
                your_guesses.append(entry)
            else:
                opponent_guesses.append(entry)

    return {
        "status": status,
        "min": MIN_NUMBER,
        "max": MAX_NUMBER,
        "current_turn_user_id": current_turn,
        "winner_id": winner_id,
        "your_secret": you.secret_number if you else None,
        "you_ready": bool(you and you.secret_number is not None),
        "opponent": (
            {
                "user_id": opponent.user_id,
                "username": opponent.user.username,
                "ready": opponent.secret_number is not None,
            }
            if opponent
            else None
        ),
        # Reveal the opponent's secret only once the game is over.
        "opponent_secret": (
            opponent.secret_number if (finished and opponent) else None
        ),
        "your_guesses": your_guesses,
        "opponent_guesses": opponent_guesses,
    }
