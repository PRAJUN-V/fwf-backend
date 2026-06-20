from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.room import GameType, RoomStatus


class RoomCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    game_type: GameType = GameType.snakes_and_ladders
    max_players: int = Field(default=2, ge=2, le=4)


class RoomPlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    username: str
    seat_order: int
    color: str


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    game_type: GameType
    max_players: int
    status: RoomStatus
    host_id: int
    created_at: datetime
    player_count: int
    players: list[RoomPlayerOut] = []
