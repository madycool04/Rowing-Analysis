from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.athlete import Athlete
from app.models.user import User, UserRole
from app.schemas.athlete import AthleteRead
from app.schemas.user import AuthResponse, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _default_athlete_name(email: str) -> str:
    """Derives a friendly default athlete name from the email local-part."""
    local_part = email.split("@")[0]
    return local_part.replace(".", " ").replace("_", " ").title() or "Athlete"


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> AuthResponse:
    normalized_email = str(payload.email).strip().lower()
    existing = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=normalized_email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        display_name=payload.display_name.strip() if payload.display_name else None,
    )
    db.add(user)
    db.flush()  # populate user.id without committing yet

    # Athlete signup auto-creates and selects a default athlete profile.
    # Coach accounts intentionally have no Athlete row.
    athlete = None
    if payload.role == UserRole.ATHLETE:
        athlete = Athlete(user_id=user.id, name=_default_athlete_name(normalized_email))
        db.add(athlete)

    db.commit()
    db.refresh(user)
    if athlete is not None:
        db.refresh(athlete)

    access_token = create_access_token(subject=str(user.id))
    return AuthResponse(
        access_token=access_token,
        user=UserRead.model_validate(user),
        athlete=AthleteRead.model_validate(athlete) if athlete is not None else None,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> AuthResponse:
    normalized_email = str(payload.email).strip().lower()
    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    athlete = None
    if user.role == UserRole.ATHLETE:
        athlete = (
            db.query(Athlete)
            .filter(Athlete.user_id == user.id)
            .order_by(Athlete.id.asc())
            .first()
        )
    if user.role == UserRole.ATHLETE and athlete is None:
        # Defensive fallback: should never happen since register() always
        # creates one, but guarantees login never 500s if data is inconsistent.
        athlete = Athlete(user_id=user.id, name=_default_athlete_name(user.email))
        db.add(athlete)
        db.commit()
        db.refresh(athlete)

    access_token = create_access_token(subject=str(user.id))
    return AuthResponse(
        access_token=access_token,
        user=UserRead.model_validate(user),
        athlete=AthleteRead.model_validate(athlete) if athlete is not None else None,
    )


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
