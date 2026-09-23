from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.user import User
    from app.models.workout import Workout


class CoachAthleteInvitation(Base):
    __tablename__ = "coach_athlete_invitations"
    __table_args__ = (
        UniqueConstraint("coach_id", "athlete_id", name="uq_coach_athlete_invitation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    coach_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    coach: Mapped["User"] = relationship(
        back_populates="coach_invitations", foreign_keys=[coach_id]
    )
    athlete: Mapped["Athlete"] = relationship(back_populates="coach_invitations")


class CoachAthleteAssignment(Base):
    __tablename__ = "coach_athlete_assignments"
    __table_args__ = (
        UniqueConstraint("coach_id", "athlete_id", name="uq_coach_athlete_assignment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    coach_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    coach: Mapped["User"] = relationship(
        back_populates="coach_assignments", foreign_keys=[coach_id]
    )
    athlete: Mapped["Athlete"] = relationship(back_populates="coach_assignments")


class WorkoutComment(Base):
    __tablename__ = "workout_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_id: Mapped[int] = mapped_column(
        ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    coach_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    coach_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    workout: Mapped["Workout"] = relationship(back_populates="coach_comments")
    coach: Mapped["User"] = relationship(
        back_populates="workout_comments", foreign_keys=[coach_id]
    )
