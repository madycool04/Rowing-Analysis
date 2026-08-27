from pydantic import BaseModel, ConfigDict

from app.models.segment import SegmentType


class SplitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ordinal: int
    distance_m: float
    elapsed_time_s: float
    pace_s_per_500: float | None
    watts: float | None
    stroke_rate: float | None
    heart_rate: int | None
    calories: float | None


class SegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ordinal: int
    type: SegmentType
    start_time_s: float
    duration_s: float
    distance_m: float
    splits: list[SplitRead] = []
