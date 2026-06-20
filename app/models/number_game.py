import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NumberGameStatus(str, enum.Enum):
    in_progress = "in_progress"
    finished = "finished"


class GuessResult(str, enum.Enum):
    low = "low"  # guess was lower than the secret -> go higher
    high = "high"  # guess was higher than the secret -> go lower
    correct = "correct"


class NumberGame(Base):
    __tablename__ = "number_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    status: Mapped[NumberGameStatus] = mapped_column(
        Enum(NumberGameStatus), default=NumberGameStatus.in_progress, nullable=False
    )
    current_turn_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    room: Mapped["Room"] = relationship("Room", back_populates="number_game")  # noqa: F821
    guesses: Mapped[list["NumberGuess"]] = relationship(
        "NumberGuess", back_populates="game", cascade="all, delete-orphan"
    )


class NumberGuess(Base):
    __tablename__ = "number_guesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("number_games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    guesser_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[GuessResult] = mapped_column(Enum(GuessResult), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    game: Mapped["NumberGame"] = relationship("NumberGame", back_populates="guesses")
