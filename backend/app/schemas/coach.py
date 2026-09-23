from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.athlete import AthleteRead
from app.schemas.workout import WorkoutListItem


class CoachAthleteSummary(BaseModel):
    athlete: AthleteRead
    recent_workout: WorkoutListItem | None
    workout_count: int
    two_k_pb_seconds: float | None


class CoachInvitationCreate(BaseModel):
    athlete_email: EmailStr


class CoachInvitationRead(BaseModel):
    id: int
    coach_id: int
    coach_name: str
    athlete_id: int
    athlete_name: str
    athlete_email: EmailStr
    created_at: datetime


class CoachConnectionRead(BaseModel):
    coach_id: int
    coach_name: str
    coach_email: EmailStr
    assigned_at: datetime


class WorkoutCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def body_must_contain_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Comment cannot be blank")
        return value


class WorkoutCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workout_id: int
    coach_id: int
    coach_name: str
    body: str
    created_at: datetime
