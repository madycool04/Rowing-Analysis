from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.workout import Workout
    from app.models.split import Split


class SegmentType(str, Enum):
    WORK = "work"
    REST = "rest"
    WARMUP = "warmup"
    COOLDOWN = "cooldown"
    OTHER = "other"


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_id: Mapped[int] = mapped_column(ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False)

    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[SegmentType] = mapped_column(String(20), nullable=False)

    start_time_s: Mapped[float] = mapped_column(Float, nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)

    workout: Mapped["Workout"] = relationship(back_populates="segments")
    splits: Mapped[list["Split"]] = relationship(
        back_populates="segment",
        cascade="all, delete-orphan",
        order_by="Split.ordinal",
    )
