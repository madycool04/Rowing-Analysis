from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_athlete, get_db
from app.models.athlete import Athlete
from app.models.segment import Segment
from app.models.workout import Workout
from app.schemas.workout import (
    WorkoutListItem,
    WorkoutListResponse,
    WorkoutManualCreate,
    WorkoutRead,
    WorkoutUploadResponse,
)
from app.services.csv_parser import CSVParseError, parse_concept2_csv
from app.services.workout_import import persist_manual_workout, persist_parsed_workout

router = APIRouter(prefix="/workouts", tags=["workouts"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB - generous for any realistic Concept2 export


def _get_owned_workout(workout_id: int, athlete: Athlete, db: Session) -> Workout:
    workout = (
        db.query(Workout)
        .options(selectinload(Workout.segments).selectinload(Segment.splits))
        .filter(Workout.id == workout_id, Workout.athlete_id == athlete.id)
        .first()
    )
    if workout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout not found")
    return workout


@router.post("/upload", response_model=WorkoutUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_workout_csv(
    file: UploadFile,
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> WorkoutUploadResponse:
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is too large.")

    try:
        parsed_list = parse_concept2_csv(contents, filename=file.filename)
    except CSVParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    import logging
    logger = logging.getLogger(__name__)

    saved_workouts = []
    warnings: list[str] = []
    
    for parsed in parsed_list:
        logger.info("CSV import: splits_detected=%d columns=%s", sum(len(seg.splits) for seg in parsed.segments), list(parsed.__dict__.keys()))
        workout_orm = persist_parsed_workout(db, athlete.id, parsed, filename=file.filename)
        workout_orm = _get_owned_workout(workout_orm.id, athlete, db)
        saved_workouts.append(WorkoutRead.model_validate(workout_orm))

        if not parsed.has_hr and "No heart-rate data found - HR-based analytics won't be available for all workouts." not in warnings:
            warnings.append("No heart-rate data found - HR-based analytics won't be available for all workouts.")
        if not parsed.has_splits and "No split-level data found - only summary analytics will be available." not in warnings:
            warnings.append("No split-level data found - only summary analytics will be available.")

    return WorkoutUploadResponse(workouts=saved_workouts, warnings=warnings)


@router.post("", response_model=WorkoutRead, status_code=status.HTTP_201_CREATED)
def create_manual_workout(
    payload: WorkoutManualCreate,
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> WorkoutRead:
    workout = persist_manual_workout(db, athlete.id, payload)
    workout = _get_owned_workout(workout.id, athlete, db)
    return WorkoutRead.model_validate(workout)


@router.get("", response_model=WorkoutListResponse)
def list_workouts(
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(
        default="newest",
        pattern="^(newest|oldest|fastest|highest_watts|longest|highest_load)$",
    ),
    has_hr: bool | None = Query(default=None),
    has_splits: bool | None = Query(default=None),
) -> WorkoutListResponse:
    q = db.query(Workout).filter(Workout.athlete_id == athlete.id)

    if has_hr is not None:
        q = q.filter(Workout.has_hr == has_hr)
    if has_splits is not None:
        q = q.filter(Workout.has_splits == has_splits)

    total = q.with_entities(func.count(Workout.id)).scalar() or 0

    # avg_pace = total_duration_s / total_distance_m (spec section 8's
    # ratio, computed at the SQL level here). Lower pace = faster = higher
    # watts, since watts and pace are inversely related - "fastest" and
    # "highest_watts" therefore sort on the same underlying expression.
    pace_ratio = Workout.total_duration_s / Workout.total_distance_m

    if sort == "newest":
        q = q.order_by(Workout.date.desc())
    elif sort == "oldest":
        q = q.order_by(Workout.date.asc())
    elif sort == "longest":
        q = q.order_by(Workout.total_duration_s.desc())
    elif sort in ("fastest", "highest_watts"):
        q = q.order_by(pace_ratio.asc())
    elif sort == "highest_load":
        # Training load isn't stored on Workout (it depends on the
        # athlete's HR profile and reference 2K, computed in Phase 6's
        # training_load service) - fall back to newest rather than
        # pretending to support a sort we can't do at the SQL level.
        q = q.order_by(Workout.date.desc())

    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return WorkoutListResponse(
        items=[WorkoutListItem.model_validate(w) for w in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{workout_id}", response_model=WorkoutRead)
def get_workout(
    workout_id: int,
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> WorkoutRead:
    workout = _get_owned_workout(workout_id, athlete, db)
    return WorkoutRead.model_validate(workout)


@router.delete("/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout(
    workout_id: int,
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> None:
    workout = _get_owned_workout(workout_id, athlete, db)
    db.delete(workout)
    db.commit()