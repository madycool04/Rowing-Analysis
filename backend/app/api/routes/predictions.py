from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_athlete, get_db
from app.models.athlete import Athlete
from app.models.segment import Segment
from app.models.workout import Workout
from app.schemas.prediction import PredictionResponse
from app.services.ml.predictor import predict_2k
from app.utils.pace import average_pace_per_500, format_pace

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/2k", response_model=PredictionResponse)
def get_2k_prediction(
    athlete: Athlete = Depends(get_current_athlete),
    db: Session = Depends(get_db),
) -> PredictionResponse:
    workouts = (
        db.query(Workout)
        .filter(Workout.athlete_id == athlete.id)
        .options(selectinload(Workout.segments).selectinload(Segment.splits))
        .order_by(Workout.date.asc())
        .all()
    )

    result = predict_2k(athlete, workouts, db=db)

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
