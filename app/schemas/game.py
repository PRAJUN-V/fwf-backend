from pydantic import BaseModel

from app.models.game import GameStatus


class GamePlayerStateOut(BaseModel):
    user_id: int
    username: str
    color: str
    seat_order: int
    position: int


class GameStateOut(BaseModel):
    room_id: int
    game_id: int
    status: GameStatus
    current_turn_user_id: int | None
    last_dice: int | None
    winner_id: int | None
    players: list[GamePlayerStateOut]
