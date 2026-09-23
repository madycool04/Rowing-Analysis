from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.coach import CoachAthleteAssignment, WorkoutComment
from app.models.user import User, UserRole
from app.models.workout import Workout
from app.schemas.coach import WorkoutCommentRead

router = APIRouter(prefix="/workouts", tags=["workout comments"])


def _can_read_workout(user: User, workout: Workout, db: Session) -> bool:
    if user.role == UserRole.ATHLETE:
        return workout.athlete.user_id == user.id
    if user.role == UserRole.COACH:
        return db.query(CoachAthleteAssignment).filter(
            CoachAthleteAssignment.coach_id == user.id,
            CoachAthleteAssignment.athlete_id == workout.athlete_id,
        ).first() is not None
    return False


@router.get("/{workout_id}/comments", response_model=list[WorkoutCommentRead])
def list_workout_comments(
    workout_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkoutCommentRead]:
    workout = db.get(Workout, workout_id)
    if workout is None or not _can_read_workout(user, workout, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout not found")
    comments = db.query(WorkoutComment).filter(
        WorkoutComment.workout_id == workout.id
    ).order_by(WorkoutComment.created_at.asc()).all()
    return [
        WorkoutCommentRead(
            id=c.id,
            workout_id=c.workout_id,
            coach_id=c.coach_id,
            coach_name=c.coach_name_snapshot,
            body=c.body,
            created_at=c.created_at,
        )
        for c in comments
    ]
