from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.athlete import Athlete
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            raise credentials_exception
        user_id = int(user_id_raw)
    except (JWTError, ValueError):
        raise credentials_exception

    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception
    return user


def get_current_athlete(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Athlete:
    """
    Returns the current user's default (first) athlete.

    Single-athlete-per-user is the primary v1 workflow (spec section 6),
    so this dependency is the convenience path used by most routes.
    Multi-athlete routes explicitly take an athlete_id and verify
    ownership instead of using this dependency.
    """
    athlete = (
        db.query(Athlete)
        .filter(Athlete.user_id == current_user.id)
        .order_by(Athlete.id.asc())
        .first()
    )
    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No athlete profile found for this user",
        )
    return athlete


def get_owned_athlete(
    athlete_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Athlete:
    """Fetch a specific athlete by id, enforcing that it belongs to the current user."""
    athlete = db.get(Athlete, athlete_id)
    if athlete is None or athlete.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Athlete not found",
        )
    return athlete
