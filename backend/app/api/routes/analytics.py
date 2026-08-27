from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_athlete, get_db
from app.models.athlete import Athlete
from app.models.segment import Segment
from app.models.workout import Workout
from app.schemas.analytics import WorkoutAnalyticsResponse
from app.services.analytics import compute_workout_analytics
from app.services.performance import build_progression_series, compute_personal_bests
from app.services.training_load import (
    build_daily_load_series,
    compute_workout_training_load,
    find_reference_2k_watts,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/workout/{workout_id}", response_model=WorkoutAnalyticsResponse)
def get_workout_analytics(
    workout_id: int,
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> WorkoutAnalyticsResponse:
    workout = (
        db.query(Workout)
        .options(selectinload(Workout.segments).selectinload(Segment.splits))
        .filter(Workout.id == workout_id, Workout.athlete_id == athlete.id)
        .first()
    )
    if workout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout not found")

    result = compute_workout_analytics(workout, athlete=athlete)
    return WorkoutAnalyticsResponse(**result)


# Phase 6 adds: GET /analytics/trends, GET /analytics/performance, GET /analytics/training-load


def _load_athlete_workouts(
    db: Session,
    athlete: Athlete,
    with_splits: bool,
    start: date_type | None = None,
    end: date_type | None = None,
) -> list[Workout]:
    q = db.query(Workout).filter(Workout.athlete_id == athlete.id)
    if start is not None:
        q = q.filter(Workout.date >= start)
    if end is not None:
        q = q.filter(Workout.date <= end)
    if with_splits:
        q = q.options(selectinload(Workout.segments).selectinload(Segment.splits))
    else:
        q = q.options(selectinload(Workout.segments))
    return q.order_by(Workout.date.asc()).all()


@router.get("/performance", response_model=WorkoutAnalyticsResponse)
def get_performance(
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> WorkoutAnalyticsResponse:
    workouts = _load_athlete_workouts(db, athlete, with_splits=False)
    personal_bests = compute_personal_bests(workouts)

    insights: list[str] = []
    for label, pb in personal_bests.items():
        if pb["improvement_s"] is not None and pb["improvement_s"] > 0:
            insights.append(
                f"Your {label.upper()} PB improved by {pb['improvement_s']:.1f}s to "
                f"{pb['current']['pace_display']}/500m."
            )

    return WorkoutAnalyticsResponse(
        metrics={"personal_bests": personal_bests},
        data_quality={"workouts_considered": len(workouts)},
        insights=insights,
    )


@router.get("/training-load", response_model=WorkoutAnalyticsResponse)
def get_training_load(
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
    start_date: date_type | None = Query(default=None),
    end_date: date_type | None = Query(default=None),
) -> WorkoutAnalyticsResponse:
    # Reference 2K uses full (unfiltered) history so a date-range filter on
    # the load series doesn't accidentally lose the athlete's best 2K.
    all_workouts = _load_athlete_workouts(db, athlete, with_splits=False)
    reference_2k_watts = find_reference_2k_watts(athlete, all_workouts)

    def _in_range(w: Workout) -> bool:
        d = w.date.date()
        if start_date is not None and d < start_date:
            return False
        if end_date is not None and d > end_date:
            return False
        return True

    workouts = [w for w in all_workouts if _in_range(w)] if (start_date or end_date) else all_workouts

    loads_by_workout: list[tuple] = []
    methods_used: dict[str, int] = {"trimp": 0, "fallback": 0, "unavailable": 0}
    for workout in workouts:
        result = compute_workout_training_load(workout, athlete, workout.avg_hr, reference_2k_watts)
        loads_by_workout.append((workout.date, result["value"]))
        methods_used[result["method"]] += 1

    series = build_daily_load_series(loads_by_workout)

    insights: list[str] = []
    if series:
        latest = series[-1]
        if latest["acwr"] is not None and latest["acwr"] > 1.5:
            insights.append(
                f"Your acute:chronic workload ratio is {latest['acwr']:.2f} - training volume has "
                "risen sharply relative to your recent baseline. This is a descriptive training-load "
                "signal, not an injury prediction."
            )

    return WorkoutAnalyticsResponse(
        metrics={"daily_series": series, "reference_2k_watts": round(reference_2k_watts, 1) if reference_2k_watts else None},
        data_quality={
            "workouts_considered": len(workouts),
            "trimp_count": methods_used["trimp"],
            "fallback_count": methods_used["fallback"],
            "unavailable_count": methods_used["unavailable"],
            "reference_2k_available": reference_2k_watts is not None,
        },
        insights=insights,
    )


@router.get("/trends", response_model=WorkoutAnalyticsResponse)
def get_trends(
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
    start_date: date_type | None = Query(default=None),
    end_date: date_type | None = Query(default=None),
) -> WorkoutAnalyticsResponse:
    workouts = _load_athlete_workouts(db, athlete, with_splits=True, start=start_date, end=end_date)

    reference_2k_watts = find_reference_2k_watts(athlete, workouts)

    watts_series = [
        {"date": w.date.isoformat(), "avg_watts": round(w.avg_watts, 1), "workout_id": w.id} for w in workouts
    ]
    hr_series = [
        {"date": w.date.isoformat(), "avg_hr": round(w.avg_hr, 1), "workout_id": w.id}
        for w in workouts
        if w.avg_hr is not None
    ]
    ef_series = [
        {
            "date": w.date.isoformat(),
            "efficiency_factor": round(w.avg_watts / w.avg_hr, 3),
            "workout_id": w.id,
        }
        for w in workouts
        if w.avg_hr
    ]

    pacing_cv_series: list[dict] = []
    interval_decay_series: list[dict] = []
    for w in workouts:
        if not w.has_splits:
            continue
        result = compute_workout_analytics(w, athlete=athlete)
        cv = result["metrics"]["pacing"]["pacing_cv_pct"]
        if cv is not None:
            pacing_cv_series.append({"date": w.date.isoformat(), "pacing_cv_pct": cv, "workout_id": w.id})
        intervals = result["metrics"]["intervals"]
        if intervals is not None:
            interval_decay_series.append(
                {
                    "date": w.date.isoformat(),
                    "slope_watts_per_interval": intervals["decay"]["slope_watts_per_interval"],
                    "workout_id": w.id,
                }
            )

    loads_by_workout = [(w.date, compute_workout_training_load(w, athlete, w.avg_hr, reference_2k_watts)["value"]) for w in workouts]
    training_load_series = build_daily_load_series(loads_by_workout)

    metrics = {
        "performance_2k": build_progression_series(workouts, "2k"),
        "performance_5k": build_progression_series(workouts, "5k"),
        "avg_watts": watts_series,
        "avg_hr": hr_series,
        "efficiency_factor": ef_series,
        "training_load": training_load_series,
        "pacing_consistency": pacing_cv_series,
        "interval_decay": interval_decay_series,
    }

    data_quality = {
        "workouts_considered": len(workouts),
        "hr_data_available": len(hr_series) > 0,
        "efficiency_factor_available": len(ef_series) > 0,
    }

    return WorkoutAnalyticsResponse(metrics=metrics, data_quality=data_quality, insights=[])
