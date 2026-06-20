"""Hand Cricket — classic 2-player finger cricket.

Rules (6 balls per innings):
- Both players show 1–6 fingers each ball simultaneously.
- Same number → batsman is OUT (innings ends).
- Different → batsman scores their finger count as runs.
- After innings 1, roles swap. Higher total after both innings wins.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hand_cricket_game import HandCricketBall, HandCricketGame, HandCricketStatus
from app.models.room import Room, RoomStatus
from app.services.room_service import RoomError

MIN_FINGERS = 1
MAX_FINGERS = 6
DEFAULT_BALLS = 6


def _players(room: Room):
    return sorted(room.players, key=lambda p: p.seat_order)


def _runs_for(game: HandCricketGame, user_id: int) -> int:
    return game.player1_runs if user_id == game.player1_id else game.player2_runs


def _add_runs(game: HandCricketGame, batsman_id: int, runs: int) -> None:
    if batsman_id == game.player1_id:
        game.player1_runs += runs
    else:
        game.player2_runs += runs


def _current_innings_runs(game: HandCricketGame) -> int:
    if game.innings == 1:
        return game.player1_runs
    return game.player2_runs


def start_game(db: Session, *, room: Room, user_id: int) -> Room:
    if room.host_id != user_id:
        raise RoomError("Only the host can start the game")
    if room.status != RoomStatus.waiting:
        raise RoomError("The game has already started")

    players = _players(room)
    if len(players) != 2:
        raise RoomError("Hand cricket needs exactly 2 players")

    p1, p2 = players[0], players[1]
    game = HandCricketGame(
        room_id=room.id,
        status=HandCricketStatus.in_progress,
        balls_per_innings=DEFAULT_BALLS,
        innings=1,
        player1_id=p1.user_id,
        player2_id=p2.user_id,
        batsman_id=p1.user_id,
        bowler_id=p2.user_id,
        ball_number=1,
    )
    db.add(game)
    room.status = RoomStatus.playing
    db.commit()
    db.refresh(room)
    return room


def _end_innings(db: Session, game: HandCricketGame, room: Room) -> None:
    if game.innings == 1:
        game.innings1_runs = _current_innings_runs(game)
        game.innings = 2
        game.ball_number = 1
        game.batsman_id, game.bowler_id = game.bowler_id, game.batsman_id
        game.status = HandCricketStatus.innings_break
        game.pending_batsman_fingers = None
        game.pending_bowler_fingers = None
    else:
        _finish_match(game)


def _finish_match(game: HandCricketGame) -> None:
    game.status = HandCricketStatus.finished
    if game.player1_runs > game.player2_runs:
        game.winner_id = game.player1_id
    elif game.player2_runs > game.player1_runs:
        game.winner_id = game.player2_id
    else:
        game.is_tie = True
        game.winner_id = None


def begin_innings_two(db: Session, *, room: Room, user_id: int) -> Room:
    game = room.hand_cricket_game
    if game is None or game.status != HandCricketStatus.innings_break:
        raise RoomError("Not between innings")
    if room.host_id != user_id:
        raise RoomError("Only the host can start the second innings")

    game.status = HandCricketStatus.in_progress
    db.commit()
    db.refresh(room)
    return room


def _resolve_ball(
    db: Session, game: HandCricketGame, room: Room, batsman_f: int, bowler_f: int
) -> None:
    is_wicket = batsman_f == bowler_f
    runs = 0 if is_wicket else batsman_f

    db.add(
        HandCricketBall(
            game_id=game.id,
            innings=game.innings,
            ball_number=game.ball_number,
            batsman_id=game.batsman_id,
            bowler_id=game.bowler_id,
            batsman_fingers=batsman_f,
            bowler_fingers=bowler_f,
            runs_scored=runs,
            is_wicket=is_wicket,
        )
    )

    if runs:
        _add_runs(game, game.batsman_id, runs)

    game.pending_batsman_fingers = None
    game.pending_bowler_fingers = None

    innings_over = is_wicket or game.ball_number >= game.balls_per_innings
    if innings_over:
        _end_innings(db, game, room)
        if game.status == HandCricketStatus.finished:
            room.status = RoomStatus.finished
    else:
        game.ball_number += 1


def reveal_fingers(db: Session, *, room: Room, user_id: int, value: int) -> Room:
    game = room.hand_cricket_game
    if game is None or game.status != HandCricketStatus.in_progress:
        raise RoomError("The game is not in progress")
    if not isinstance(value, int) or value < MIN_FINGERS or value > MAX_FINGERS:
        raise RoomError(f"Show between {MIN_FINGERS} and {MAX_FINGERS} fingers")

    if user_id == game.batsman_id:
        if game.pending_batsman_fingers is not None:
            raise RoomError("You already showed your fingers")
        game.pending_batsman_fingers = value
    elif user_id == game.bowler_id:
        if game.pending_bowler_fingers is not None:
            raise RoomError("You already showed your fingers")
        game.pending_bowler_fingers = value
    else:
        raise RoomError("You are not batting or bowling this ball")

    if (
        game.pending_batsman_fingers is not None
        and game.pending_bowler_fingers is not None
    ):
        _resolve_ball(
            db,
            game,
            room,
            game.pending_batsman_fingers,
            game.pending_bowler_fingers,
        )

    db.commit()
    db.refresh(room)
    return room


def serialize_state(db: Session, room: Room, viewer_id: int) -> dict:
    game = room.hand_cricket_game
    players = _players(room)
    username_by_id = {p.user_id: p.user.username for p in players}

    if game is None:
        return {"status": "waiting"}

    balls = list(
        db.scalars(
            select(HandCricketBall)
            .where(HandCricketBall.game_id == game.id)
            .order_by(HandCricketBall.id)
        )
    )

    last_ball = None
    if balls:
        b = balls[-1]
        last_ball = {
            "innings": b.innings,
            "ball_number": b.ball_number,
            "batsman_fingers": b.batsman_fingers,
            "bowler_fingers": b.bowler_fingers,
            "runs_scored": b.runs_scored,
            "is_wicket": b.is_wicket,
            "batsman_name": username_by_id.get(b.batsman_id, "?"),
        }

    you_submitted = False
    opponent_submitted = False
    your_fingers: int | None = None

    if game.status == HandCricketStatus.in_progress:
        if viewer_id == game.batsman_id:
            you_submitted = game.pending_batsman_fingers is not None
            opponent_submitted = game.pending_bowler_fingers is not None
            your_fingers = game.pending_batsman_fingers
        elif viewer_id == game.bowler_id:
            you_submitted = game.pending_bowler_fingers is not None
            opponent_submitted = game.pending_batsman_fingers is not None
            your_fingers = game.pending_bowler_fingers

    role: str | None = None
    if viewer_id == game.batsman_id:
        role = "bat"
    elif viewer_id == game.bowler_id:
        role = "bowl"

    return {
        "status": game.status.value,
        "innings": game.innings,
        "balls_per_innings": game.balls_per_innings,
        "ball_number": game.ball_number,
        "batsman_id": game.batsman_id,
        "bowler_id": game.bowler_id,
        "batsman_name": username_by_id.get(game.batsman_id, "?"),
        "bowler_name": username_by_id.get(game.bowler_id, "?"),
        "your_role": role,
        "player1_id": game.player1_id,
        "player2_id": game.player2_id,
        "player1_name": username_by_id.get(game.player1_id, "?"),
        "player2_name": username_by_id.get(game.player2_id, "?"),
        "player1_runs": game.player1_runs,
        "player2_runs": game.player2_runs,
        "innings1_runs": game.innings1_runs,
        "you_submitted": you_submitted,
        "opponent_submitted": opponent_submitted,
        "your_fingers": your_fingers,
        "last_ball": last_ball,
        "winner_id": game.winner_id,
        "is_tie": game.is_tie,
        "ball_history": [
            {
                "innings": b.innings,
                "ball_number": b.ball_number,
                "batsman_fingers": b.batsman_fingers,
                "bowler_fingers": b.bowler_fingers,
                "runs_scored": b.runs_scored,
                "is_wicket": b.is_wicket,
            }
            for b in balls
        ],
    }
