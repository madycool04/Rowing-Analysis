from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_athlete
from app.db.session import get_db
from app.models.athlete import Athlete
from app.models.user import User
from app.schemas.athlete import AthleteRead, AthleteUpdate

router = APIRouter(prefix="/athletes", tags=["athletes"])


@router.get("", response_model=list[AthleteRead])
def list_athletes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AthleteRead]:
    athletes = (
        db.query(Athlete)
        .filter(Athlete.user_id == current_user.id)
        .order_by(Athlete.id.asc())
        .all()
    )
    return [AthleteRead.model_validate(a) for a in athletes]


@router.get("/{athlete_id}", response_model=AthleteRead)
def get_athlete(athlete: Athlete = Depends(get_owned_athlete)) -> AthleteRead:
    return AthleteRead.model_validate(athlete)


@router.patch("/{athlete_id}", response_model=AthleteRead)
def update_athlete(
    payload: AthleteUpdate,
    athlete: Athlete = Depends(get_owned_athlete),
    db: Session = Depends(get_db),
) -> AthleteRead:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(athlete, field, value)
    db.add(athlete)
    db.commit()
    db.refresh(athlete)
    return AthleteRead.model_validate(athlete)
