from pydantic import BaseModel


class ContributingFactor(BaseModel):
    factor: str
    trend: str  # "positive" | "negative" | "unchanged" | "up" | "down"


class PredictionResponse(BaseModel):
    available: bool
    reason: str | None = None

    predicted_time_s: float | None = None
    predicted_pace_display: str | None = None
    target_distance_m: float | None = None

    lower_bound_s: float | None = None
    upper_bound_s: float | None = None
    confidence: str | None = None  # "low" | "moderate" | "high"

    method_used: str | None = None
    n_historical_2k_tests: int = 0
    sufficient_data_for_ml: bool = False

    change_vs_previous_s: float | None = None
    contributing_factors: list[ContributingFactor] = []

    note: str | None = None
