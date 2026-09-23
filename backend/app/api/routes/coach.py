from datetime import date, datetime, time, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_coach, get_db, require_assigned_athlete
from app.api.routes.analytics import get_performance, get_training_load, get_trends
from app.models.athlete import Athlete
from app.models.coach import CoachAthleteAssignment, CoachAthleteInvitation, WorkoutComment
from app.models.segment import Segment
from app.models.user import User, UserRole
from app.models.workout import Workout
from app.schemas.analytics import WorkoutAnalyticsResponse
from app.schemas.athlete import AthleteRead
from app.schemas.coach import (
    CoachAthleteSummary,
    CoachInvitationCreate,
    CoachInvitationRead,
    WorkoutCommentCreate,
    WorkoutCommentRead,
)
from app.schemas.prediction import PredictionResponse
from app.schemas.workout import WorkoutListItem, WorkoutListResponse, WorkoutRead
from app.services.analytics import compute_workout_analytics
from app.services.ml.predictor import predict_2k
from app.services.pdf_report import build_athlete_report_pdf
from app.services.performance import compute_personal_bests
from app.utils.pace import average_pace_per_500, format_pace

router = APIRouter(prefix="/coach", tags=["coach"])


def _invitation_read(invitation: CoachAthleteInvitation) -> CoachInvitationRead:
    return CoachInvitationRead(
        id=invitation.id,
        coach_id=invitation.coach_id,
        coach_name=invitation.coach.display_name or invitation.coach.email,
        athlete_id=invitation.athlete_id,
        athlete_name=invitation.athlete.name,
        athlete_email=invitation.athlete.user.email,
        created_at=invitation.created_at,
    )


@router.get("/invitations", response_model=list[CoachInvitationRead])
def list_sent_invitations(
    coach: User = Depends(get_current_coach),
    db: Session = Depends(get_db),
) -> list[CoachInvitationRead]:
    invitations = db.query(CoachAthleteInvitation).filter(
        CoachAthleteInvitation.coach_id == coach.id
    ).order_by(CoachAthleteInvitation.created_at.desc()).all()
    return [_invitation_read(invitation) for invitation in invitations]


@router.post("/invitations", response_model=CoachInvitationRead, status_code=status.HTTP_201_CREATED)
def invite_athlete(
    payload: CoachInvitationCreate,
    coach: User = Depends(get_current_coach),
    db: Session = Depends(get_db),
) -> CoachInvitationRead:
    normalized_email = str(payload.athlete_email).strip().lower()
    athlete_user = db.query(User).filter(
        func.lower(User.email) == normalized_email,
        User.role == UserRole.ATHLETE,
    ).first()
    athlete = None
    if athlete_user is not None:
        athlete = db.query(Athlete).filter(Athlete.user_id == athlete_user.id).order_by(Athlete.id).first()
    if athlete is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Athlete account not found")
    if db.query(CoachAthleteAssignment).filter_by(coach_id=coach.id, athlete_id=athlete.id).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This athlete is already assigned to you")
    if db.query(CoachAthleteInvitation).filter_by(coach_id=coach.id, athlete_id=athlete.id).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An invitation is already pending")
    invitation = CoachAthleteInvitation(coach_id=coach.id, athlete_id=athlete.id)
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return _invitation_read(invitation)


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_invitation(
    invitation_id: int,
    coach: User = Depends(get_current_coach),
    db: Session = Depends(get_db),
) -> None:
    invitation = db.query(CoachAthleteInvitation).filter_by(
        id=invitation_id, coach_id=coach.id
    ).first()
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    db.delete(invitation)
    db.commit()


def _assigned_workout(workout_id: int, athlete: Athlete, db: Session) -> Workout:
    workout = (
        db.query(Workout)
        .options(selectinload(Workout.segments).selectinload(Segment.splits))
        .filter(Workout.id == workout_id, Workout.athlete_id == athlete.id)
        .first()
    )
    if workout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout not found")
    return workout


@router.get("/athletes", response_model=list[CoachAthleteSummary])
def list_assigned_athletes(
    coach: User = Depends(get_current_coach),
    db: Session = Depends(get_db),
) -> list[CoachAthleteSummary]:
    athletes = (
        db.query(Athlete)
        .join(CoachAthleteAssignment, CoachAthleteAssignment.athlete_id == Athlete.id)
        .filter(CoachAthleteAssignment.coach_id == coach.id)
        .order_by(Athlete.name.asc())
        .all()
    )
    result = []
    for athlete in athletes:
        workouts = (
            db.query(Workout)
            .options(selectinload(Workout.segments))
            .filter(Workout.athlete_id == athlete.id)
            .order_by(Workout.date.desc())
            .all()
        )
        pbs = compute_personal_bests(workouts)
        result.append(CoachAthleteSummary(
            athlete=AthleteRead.model_validate(athlete),
            recent_workout=WorkoutListItem.model_validate(workouts[0]) if workouts else None,
            workout_count=len(workouts),
            two_k_pb_seconds=pbs.get("2k", {}).get("current", {}).get("duration_s"),
        ))
    return result


@router.get("/athletes/{athlete_id}", response_model=AthleteRead)
def get_assigned_athlete(athlete: Athlete = Depends(require_assigned_athlete)) -> AthleteRead:
    return AthleteRead.model_validate(athlete)


@router.delete("/athletes/{athlete_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_athlete_assignment(
    athlete: Athlete = Depends(require_assigned_athlete),
    coach: User = Depends(get_current_coach),
    db: Session = Depends(get_db),
) -> None:
    assignment = db.query(CoachAthleteAssignment).filter_by(
        coach_id=coach.id, athlete_id=athlete.id
    ).first()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    db.delete(assignment)
    db.commit()


@router.get("/athletes/{athlete_id}/workouts", response_model=WorkoutListResponse)
def list_assigned_athlete_workouts(
    athlete: Athlete = Depends(require_assigned_athlete),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> WorkoutListResponse:
    q = db.query(Workout).filter(Workout.athlete_id == athlete.id)
    total = q.with_entities(func.count(Workout.id)).scalar() or 0
    workouts = q.order_by(Workout.date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return WorkoutListResponse(
        items=[WorkoutListItem.model_validate(w) for w in workouts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/athletes/{athlete_id}/workouts/{workout_id}", response_model=WorkoutRead)
def get_assigned_athlete_workout(
    workout_id: int,
    athlete: Athlete = Depends(require_assigned_athlete),
    db: Session = Depends(get_db),
) -> WorkoutRead:
    return WorkoutRead.model_validate(_assigned_workout(workout_id, athlete, db))


@router.get("/athletes/{athlete_id}/workouts/{workout_id}/analytics", response_model=WorkoutAnalyticsResponse)
def get_assigned_workout_analytics(
    workout_id: int,
    athlete: Athlete = Depends(require_assigned_athlete),
    db: Session = Depends(get_db),
) -> WorkoutAnalyticsResponse:
    return WorkoutAnalyticsResponse(**compute_workout_analytics(_assigned_workout(workout_id, athlete, db), athlete=athlete))


@router.get("/athletes/{athlete_id}/analytics/performance", response_model=WorkoutAnalyticsResponse)
def assigned_performance(athlete: Athlete = Depends(require_assigned_athlete), db: Session = Depends(get_db)):
    return get_performance(athlete=athlete, db=db)


@router.get("/athletes/{athlete_id}/analytics/training-load", response_model=WorkoutAnalyticsResponse)
def assigned_training_load(
    athlete: Athlete = Depends(require_assigned_athlete),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    return get_training_load(athlete=athlete, db=db, start_date=start_date, end_date=end_date)


@router.get("/athletes/{athlete_id}/analytics/trends", response_model=WorkoutAnalyticsResponse)
def assigned_trends(
    athlete: Athlete = Depends(require_assigned_athlete),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    return get_trends(athlete=athlete, db=db, start_date=start_date, end_date=end_date)


@router.get("/athletes/{athlete_id}/predictions/2k", response_model=PredictionResponse)
def assigned_prediction(athlete: Athlete = Depends(require_assigned_athlete), db: Session = Depends(get_db)):
    workouts = db.query(Workout).filter(Workout.athlete_id == athlete.id).options(
        selectinload(Workout.segments).selectinload(Segment.splits)
    ).order_by(Workout.date.asc()).all()
    result = predict_2k(athlete, workouts, db=None)
    if not result["available"]:
        return PredictionResponse(available=False, reason=result.get("reason"))
    pace = average_pace_per_500(2000.0, result["predicted_time_s"])
    return PredictionResponse(
        available=True,
        predicted_time_s=result["predicted_time_s"],
        predicted_pace_display=format_pace(pace),
        target_distance_m=result["target_distance_m"],
        lower_bound_s=result["lower_bound_s"],
        upper_bound_s=result["upper_bound_s"],
        confidence=result["confidence"],
        method_used=result["method_used"],
        n_historical_2k_tests=result["n_historical_2k_tests"],
        sufficient_data_for_ml=result["sufficient_data_for_ml"],
        change_vs_previous_s=result["change_vs_previous_s"],
        contributing_factors=result["contributing_factors"],
        note=result["note"],
    )


@router.post("/athletes/{athlete_id}/workouts/{workout_id}/comments", response_model=WorkoutCommentRead, status_code=status.HTTP_201_CREATED)
def add_workout_comment(
    workout_id: int,
    payload: WorkoutCommentCreate,
    athlete: Athlete = Depends(require_assigned_athlete),
    coach: User = Depends(get_current_coach),
    db: Session = Depends(get_db),
) -> WorkoutCommentRead:
    workout = _assigned_workout(workout_id, athlete, db)
    name = coach.display_name or coach.email
    comment = WorkoutComment(
        workout_id=workout.id,
        coach_id=coach.id,
        coach_name_snapshot=name,
        body=payload.body.strip(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return WorkoutCommentRead(
        id=comment.id,
        workout_id=comment.workout_id,
        coach_id=comment.coach_id,
        coach_name=comment.coach_name_snapshot,
        body=comment.body,
        created_at=comment.created_at,
    )


@router.get("/athletes/{athlete_id}/report.pdf")
def export_athlete_report(
    athlete: Athlete = Depends(require_assigned_athlete),
    db: Session = Depends(get_db),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> Response:
    today = datetime.now(timezone.utc).date()
    end = end_date or today
    start = start_date or (end - timedelta(days=27))
    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if (end - start).days > 366:
        raise HTTPException(status_code=422, detail="Report range cannot exceed 12 months")
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end, time.max, tzinfo=timezone.utc)
    workouts = db.query(Workout).options(
        selectinload(Workout.segments).selectinload(Segment.splits)
    ).filter(
        Workout.athlete_id == athlete.id,
        Workout.date >= start_dt,
        Workout.date <= end_dt,
    ).order_by(Workout.date.asc()).all()
    all_workouts = db.query(Workout).options(
        selectinload(Workout.segments).selectinload(Segment.splits)
    ).filter(Workout.athlete_id == athlete.id).order_by(Workout.date.asc()).all()
    workout_ids = [w.id for w in workouts]
    comments = []
    if workout_ids:
        comments = db.query(WorkoutComment).filter(
            WorkoutComment.workout_id.in_(workout_ids)
        ).order_by(WorkoutComment.created_at.asc()).all()
    pdf = build_athlete_report_pdf(
        athlete=athlete,
        workouts=workouts,
        all_workouts=all_workouts,
        comments=comments,
        start_date=start,
        end_date=end,
        generated_at=datetime.now(timezone.utc),
    )
    safe_name = "".join(c if c.isalnum() else "-" for c in athlete.name).strip("-").lower() or "athlete"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="oarsight-{safe_name}-report.pdf"',
            "Cache-Control": "private, no-store",
        },
    )
