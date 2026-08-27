from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.segment import Segment


class Split(Base):
    __tablename__ = "splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id", ondelete="CASCADE"), nullable=False)

    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    elapsed_time_s: Mapped[float] = mapped_column(Float, nullable=False)

    # Canonical performance value is watts (see spec section 8). Pace is
    # derived from watts where needed rather than stored as the source of
    # truth, but we persist it too since it's what Concept2 CSVs report
    # directly and rowers read pace at a glance.
    pace_s_per_500: Mapped[float | None] = mapped_column(Float, nullable=True)
    watts: Mapped[float | None] = mapped_column(Float, nullable=True)

    stroke_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calories: Mapped[float | None] = mapped_column(Float, nullable=True)

    segment: Mapped["Segment"] = relationship(back_populates="splits")
