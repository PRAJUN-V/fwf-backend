import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GameType(str, enum.Enum):
    snakes_and_ladders = "snakes_and_ladders"
    ludo = "ludo"
    number_prediction = "number_prediction"
    hand_cricket = "hand_cricket"


class RoomStatus(str, enum.Enum):
    waiting = "waiting"
    playing = "playing"
    finished = "finished"


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str | None] = mapped_column(String(12), unique=True, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    game_type: Mapped[GameType] = mapped_column(
        Enum(GameType), default=GameType.snakes_and_ladders, nullable=False
    )
    max_players: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    status: Mapped[RoomStatus] = mapped_column(
        Enum(RoomStatus), default=RoomStatus.waiting, nullable=False, index=True
    )
    host_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    host: Mapped["User"] = relationship("User")  # noqa: F821
    players: Mapped[list["RoomPlayer"]] = relationship(  # noqa: F821
        "RoomPlayer", back_populates="room", cascade="all, delete-orphan"
    )
    game: Mapped["Game | None"] = relationship(  # noqa: F821
        "Game", back_populates="room", uselist=False, cascade="all, delete-orphan"
    )
    number_game: Mapped["NumberGame | None"] = relationship(  # noqa: F821
        "NumberGame", back_populates="room", uselist=False, cascade="all, delete-orphan"
    )
    hand_cricket_game: Mapped["HandCricketGame | None"] = relationship(  # noqa: F821
        "HandCricketGame", back_populates="room", uselist=False, cascade="all, delete-orphan"
    )
