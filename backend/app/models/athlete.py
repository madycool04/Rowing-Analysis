from datetime import date, datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workout import Workout
    from app.models.prediction import Prediction


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class TrainingLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    ELITE = "elite"


# Default 5-zone %HRmax model (see section 13 of the spec).
# Values are the lower bound of each zone as a fraction of HRmax.
DEFAULT_HR_ZONE_CONFIG: dict[str, Any] = {
    "model": "percent_hrmax",
    "zones": [
        {"zone": 1, "label": "Zone 1", "lower_pct": 0.50, "upper_pct": 0.60},
        {"zone": 2, "label": "Zone 2", "lower_pct": 0.60, "upper_pct": 0.70},
        {"zone": 3, "label": "Zone 3", "lower_pct": 0.70, "upper_pct": 0.80},
        {"zone": 4, "label": "Zone 4", "lower_pct": 0.80, "upper_pct": 0.90},
        {"zone": 5, "label": "Zone 5", "lower_pct": 0.90, "upper_pct": 1.10},
    ],
}


class Athlete(Base):
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    sex: Mapped[Sex | None] = mapped_column(String(20), nullable=True)

    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)

    resting_hr: Mapped[int | None] = mapped_column(nullable=True)
    max_hr: Mapped[int | None] = mapped_column(nullable=True)

    best_2k_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    training_level: Mapped[TrainingLevel | None] = mapped_column(String(20), nullable=True)

    hr_zone_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=lambda: DEFAULT_HR_ZONE_CONFIG)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship(back_populates="athletes")
    workouts: Mapped[list["Workout"]] = relationship(
        back_populates="athlete", cascade="all, delete-orphan"
    )
    predictions: Mapped[list["Prediction"]] = relationship(
        back_populates="athlete", cascade="all, delete-orphan"
    )
