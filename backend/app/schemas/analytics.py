from typing import Any

from pydantic import BaseModel


class DataQualityNote(BaseModel):
    """A single flag explaining why a metric is or isn't available."""

    available: bool
    reason: str | None = None


class WorkoutAnalyticsResponse(BaseModel):
    """
    Stable envelope for every analytics endpoint (spec section 10):

        { "metrics": {...}, "data_quality": {...}, "insights": [...] }

    `metrics` and `data_quality` are intentionally loosely typed (dict)
    because the set of computable metrics varies per workout depending on
    what data is available - forcing a rigid schema would mean either
    fabricating placeholder values or scattering optional fields
    everywhere. The envelope shape itself is what stays stable.
    """

    metrics: dict[str, Any]
    data_quality: dict[str, Any]
    insights: list[str]
