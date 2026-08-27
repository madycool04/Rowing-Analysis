from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.pace import average_pace_per_500, format_pace, watts_from_pace_per_500

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.segment import Segment


class WorkoutSource(str, Enum):
    CONCEPT2_CSV_SUMMARY = "concept2_csv_summary"
    CONCEPT2_CSV_DETAILED = "concept2_csv_detailed"
    MANUAL = "manual"
    GENERATED_SAMPLE = "generated_sample"


class WorkoutCategory(str, Enum):
    """
    High-level shape of the workout, inferred from its segments rather
    than modeled with separate database logic (spec section 7).
    """

    CONTINUOUS = "continuous"
    INTERVAL = "interval"
    MIXED = "mixed"
    OTHER = "other"


class Workout(Base):
    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False)

    source: Mapped[WorkoutSource] = mapped_column(String(30), nullable=False)
    category: Mapped[WorkoutCategory] = mapped_column(String(20), nullable=False, default=WorkoutCategory.OTHER)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    total_distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    total_duration_s: Mapped[float] = mapped_column(Float, nullable=False)

    # --- Data quality (spec section 10): first-class fields checked by
    # every analytics computation before it runs. ---
    has_hr: Mapped[bool] = mapped_column(Boolean, default=False)
    hr_coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_splits: Mapped[bool] = mapped_column(Boolean, default=False)
    split_granularity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    has_power: Mapped[bool] = mapped_column(Boolean, default=False)
    has_distance: Mapped[bool] = mapped_column(Boolean, default=True)
    has_stroke_rate: Mapped[bool] = mapped_column(Boolean, default=False)

    # Aggregate HR/stroke-rate, persisted at import time (spec section 9-10).
    # These CANNOT always be derived on demand: a summary-only CSV or a
    # manual entry has no split rows to average over, so the aggregate
    # value from the source (or computed once from splits at import time)
    # is stored here directly. avg_pace/avg_watts are NOT stored - they're
    # always exactly derivable from total_distance_m/total_duration_s (see
    # the properties below), so persisting them would just be duplicated,
    # driftable data.
    avg_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_stroke_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    raw_source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    athlete: Mapped["Athlete"] = relationship(back_populates="workouts")
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="workout",
        cascade="all, delete-orphan",
        order_by="Segment.ordinal",
    )

    @property
    def avg_pace_s_per_500(self) -> float:
        """Always exact: total elapsed time / total distance (spec section 8) - never averaged from splits."""
        return average_pace_per_500(self.total_distance_m, self.total_duration_s)

    @property
    def avg_pace_display(self) -> str | None:
        return format_pace(self.avg_pace_s_per_500)

    @property
    def avg_watts(self) -> float:
        return watts_from_pace_per_500(self.avg_pace_s_per_500)
