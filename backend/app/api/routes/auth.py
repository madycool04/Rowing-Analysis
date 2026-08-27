from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.athlete import Athlete
from app.models.user import User
from app.schemas.athlete import AthleteRead
from app.schemas.user import AuthResponse, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _default_athlete_name(email: str) -> str:
    """Derives a friendly default athlete name from the email local-part."""
    local_part = email.split("@")[0]
    return local_part.replace(".", " ").replace("_", " ").title() or "Athlete"


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> AuthResponse:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    db.flush()  # populate user.id without committing yet

    # Spec section 5: signup MUST auto-create and auto-select a default
    # athlete profile so the user never sees an empty athlete-selection screen.
    athlete = Athlete(user_id=user.id, name=_default_athlete_name(payload.email))
    db.add(athlete)

    db.commit()
    db.refresh(user)
    db.refresh(athlete)

    access_token = create_access_token(subject=str(user.id))
    return AuthResponse(
        access_token=access_token,
        user=UserRead.model_validate(user),
        athlete=AthleteRead.model_validate(athlete),
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    athlete = (
        db.query(Athlete)
        .filter(Athlete.user_id == user.id)
        .order_by(Athlete.id.asc())
        .first()
    )
    if athlete is None:
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
        athlete=AthleteRead.model_validate(athlete),
    )


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
