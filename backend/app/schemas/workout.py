from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.segment import SegmentType
from app.models.workout import WorkoutCategory, WorkoutSource
from app.schemas.segment import SegmentRead


class WorkoutListItem(BaseModel):
    """Lightweight representation used by list/history endpoints - no segments/splits."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    date: datetime
    category: WorkoutCategory
    total_distance_m: float
    total_duration_s: float
    avg_pace_s_per_500: float
    avg_pace_display: str | None
    avg_watts: float
    avg_hr: float | None
    avg_stroke_rate: float | None
    has_hr: bool
    has_splits: bool
    has_power: bool
    has_stroke_rate: bool


class WorkoutRead(WorkoutListItem):
    source: WorkoutSource
    hr_coverage_pct: float | None
    split_granularity: str | None
    has_distance: bool
    created_at: datetime
    segments: list[SegmentRead] = []


class WorkoutListResponse(BaseModel):
    """Paginated list envelope (spec section 29: History page requires pagination)."""

    items: list[WorkoutListItem]
    total: int
    page: int
    page_size: int


class ManualSplitInput(BaseModel):
    ordinal: int = Field(ge=1)
    distance_m: float = Field(gt=0)
    elapsed_time_s: float = Field(gt=0)
    watts: float | None = Field(default=None, ge=0)
    stroke_rate: float | None = Field(default=None, gt=0)
    heart_rate: int | None = Field(default=None, gt=0, lt=250)
    calories: float | None = Field(default=None, ge=0)


class ManualSegmentInput(BaseModel):
    type: SegmentType = SegmentType.WORK
    splits: list[ManualSplitInput] = Field(min_length=1)

    @property
    def distance_m(self) -> float:
        return sum(s.distance_m for s in self.splits)

    @property
    def duration_s(self) -> float:
        return sum(s.elapsed_time_s for s in self.splits)


class WorkoutManualCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    date: datetime
    category: WorkoutCategory | None = None
    segments: list[ManualSegmentInput] = Field(min_length=1)


class WorkoutUploadResponse(BaseModel):
    """Returned after a successful CSV upload/import - drives the Upload page's confirmation view."""

    workouts: list[WorkoutRead]
    warnings: list[str] = []