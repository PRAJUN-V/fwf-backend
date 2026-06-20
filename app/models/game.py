import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GameStatus(str, enum.Enum):
    in_progress = "in_progress"
    finished = "finished"


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    status: Mapped[GameStatus] = mapped_column(
        Enum(GameStatus), default=GameStatus.in_progress, nullable=False
    )
    current_turn_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_dice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    room: Mapped["Room"] = relationship("Room", back_populates="game")  # noqa: F821
    player_states: Mapped[list["GamePlayerState"]] = relationship(
        "GamePlayerState", back_populates="game", cascade="all, delete-orphan"
    )


class GamePlayerState(Base):
    __tablename__ = "game_player_states"
    __table_args__ = (UniqueConstraint("game_id", "user_id", name="uq_game_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    seat_order: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    game: Mapped["Game"] = relationship("Game", back_populates="player_states")
    user: Mapped["User"] = relationship("User")  # noqa: F821
