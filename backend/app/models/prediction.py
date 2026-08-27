from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False)

    model_name: Mapped[str] = mapped_column(String(50), nullable=False)  # "previous_2k" | "pauls_law" | "ridge" | ...
    model_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")

    prediction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    target_distance_m: Mapped[float] = mapped_column(Float, nullable=False, default=2000.0)

    predicted_time_s: Mapped[float] = mapped_column(Float, nullable=False)
    lower_bound_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_bound_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)  # "low" | "moderate" | "high"

    features_used: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    athlete: Mapped["Athlete"] = relationship(back_populates="predictions")
