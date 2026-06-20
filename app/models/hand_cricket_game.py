import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HandCricketStatus(str, enum.Enum):
    in_progress = "in_progress"
    innings_break = "innings_break"
    finished = "finished"


class HandCricketGame(Base):
    __tablename__ = "hand_cricket_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    status: Mapped[HandCricketStatus] = mapped_column(
        Enum(HandCricketStatus), default=HandCricketStatus.in_progress, nullable=False
    )
    balls_per_innings: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    innings: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    batsman_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    bowler_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ball_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    player1_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    player2_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    player1_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    player2_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    innings1_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_batsman_fingers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_bowler_fingers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_tie: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    room: Mapped["Room"] = relationship("Room", back_populates="hand_cricket_game")  # noqa: F821
    balls: Mapped[list["HandCricketBall"]] = relationship(
        "HandCricketBall", back_populates="game", cascade="all, delete-orphan"
    )


class HandCricketBall(Base):
    __tablename__ = "hand_cricket_balls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("hand_cricket_games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    innings: Mapped[int] = mapped_column(Integer, nullable=False)
    ball_number: Mapped[int] = mapped_column(Integer, nullable=False)
    batsman_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    bowler_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    batsman_fingers: Mapped[int] = mapped_column(Integer, nullable=False)
    bowler_fingers: Mapped[int] = mapped_column(Integer, nullable=False)
    runs_scored: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_wicket: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    game: Mapped["HandCricketGame"] = relationship("HandCricketGame", back_populates="balls")
