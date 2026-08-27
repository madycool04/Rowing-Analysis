from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.athlete import DEFAULT_HR_ZONE_CONFIG, Sex, TrainingLevel


class AthleteBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    date_of_birth: date | None = None
    sex: Sex | None = None
    weight_kg: float | None = Field(default=None, gt=0)
    height_cm: float | None = Field(default=None, gt=0)
    resting_hr: int | None = Field(default=None, gt=0, lt=250)
    max_hr: int | None = Field(default=None, gt=0, lt=250)
    best_2k_seconds: float | None = Field(default=None, gt=0)
    training_level: TrainingLevel | None = None


class AthleteCreate(AthleteBase):
    hr_zone_config: dict[str, Any] = Field(default_factory=lambda: DEFAULT_HR_ZONE_CONFIG)


class AthleteUpdate(BaseModel):
    """All fields optional - only supplied fields are updated."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    date_of_birth: date | None = None
    sex: Sex | None = None
    weight_kg: float | None = Field(default=None, gt=0)
    height_cm: float | None = Field(default=None, gt=0)
    resting_hr: int | None = Field(default=None, gt=0, lt=250)
    max_hr: int | None = Field(default=None, gt=0, lt=250)
    best_2k_seconds: float | None = Field(default=None, gt=0)
    training_level: TrainingLevel | None = None
    hr_zone_config: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_hr_pair(self):
        if self.resting_hr is not None and self.max_hr is not None and self.max_hr <= self.resting_hr:
            raise ValueError("Maximum HR must be greater than resting HR.")
        return self


class AthleteRead(AthleteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    hr_zone_config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
