from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.coach import CoachAthleteAssignment, CoachAthleteInvitation, WorkoutComment


class UserRole(str, Enum):
    ATHLETE = "athlete"
    COACH = "coach"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        String(20), nullable=False, default=UserRole.ATHLETE, server_default=UserRole.ATHLETE.value
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    athletes: Mapped[list["Athlete"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    coach_assignments: Mapped[list["CoachAthleteAssignment"]] = relationship(
        back_populates="coach",
        cascade="all, delete-orphan",
        foreign_keys="CoachAthleteAssignment.coach_id",
    )
    coach_invitations: Mapped[list["CoachAthleteInvitation"]] = relationship(
        back_populates="coach",
        cascade="all, delete-orphan",
        foreign_keys="CoachAthleteInvitation.coach_id",
    )
    workout_comments: Mapped[list["WorkoutComment"]] = relationship(
        back_populates="coach", foreign_keys="WorkoutComment.coach_id"
    )
