from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.athlete import AthleteRead
from app.models.user import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.ATHLETE
    display_name: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def coach_requires_name(self):
        if self.role == UserRole.COACH and not (self.display_name or "").strip():
            raise ValueError("Coach name is required")
        return self


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole
    display_name: str | None
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str | None = None


class AuthResponse(BaseModel):
    """
    Returned on successful register/login.

    Athlete registration includes the auto-created athlete profile.
    Coach registration returns ``athlete=None``.
    """

    access_token: str
    token_type: str = "bearer"
    user: UserRead
    athlete: AthleteRead | None
