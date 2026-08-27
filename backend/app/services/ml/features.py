"""
Feature engineering for 2K prediction (spec section 21).

CRITICAL: every feature here is computed using ONLY workouts strictly
before the target date passed in. No feature may read the target
workout's own values (that would leak the answer - a 2K's own average
watts, for instance, is a near-exact function of its time). Callers in
train.py and predictor.py must always pass a target_date that excludes
the workout being predicted, and this module never receives the target
workout itself as an input - only the athlete, the candidate pool of
prior workouts, and a cutoff date.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models.athlete import Athlete
from app.models.workout import Workout
from app.services.analytics import compute_workout_analytics
from app.services.hr_zones import compute_efficiency_factor, compute_hr_drift
from app.services.ml.baselines import REFERENCE_DISTANCES_M, TARGET_DISTANCE_M, _qualifying_efforts_before
from app.services.training_load import build_daily_load_series, compute_workout_training_load, find_reference_2k_watts
from app.utils.pace import average_pace_per_500

LOOKBACK_DAYS = 42  # ~6 weeks - the window used for "recent" training-volume aggregates

FEATURE_NAMES: list[str] = [
    "recent_2k_pace",
    "recent_5k_pace",
    "recent_6k_pace",
    "recent_10k_pace",
    "best_recent_watts",
    "avg_watts",
    "avg_workout_duration_s",
    "avg_workout_distance_m",
    "avg_hr",
    "max_hr",
    "hr_drift_pct",
    "efficiency_factor",
    "pacing_consistency_cv_pct",
    "interval_decay_slope",
    "recent_training_load",
    "training_load_7day",
    "training_load_28day",
    "athlete_weight_kg",
    "avg_stroke_rate",
]


def _workouts_before(workouts: list[Workout], target_date: datetime) -> list[Workout]:
    return [w for w in workouts if w.date < target_date]


def _recent_window(workouts: list[Workout], target_date: datetime, days: int = LOOKBACK_DAYS) -> list[Workout]:
    cutoff = target_date - timedelta(days=days)
    return [w for w in workouts if cutoff <= w.date < target_date]


def _most_recent_pace_for_distance(workouts: list[Workout], target_date: datetime, distance_m: float) -> float | None:
    efforts = _qualifying_efforts_before(workouts, distance_m, target_date)
    if not efforts:
        return None
    most_recent = max(efforts, key=lambda e: e.date)
    return average_pace_per_500(most_recent.distance_m, most_recent.duration_s)


def build_feature_vector(
    athlete: Athlete,
    all_workouts: list[Workout],
    target_date: datetime,
) -> dict[str, float | None]:
    """
    Builds the feature dict for predicting a 2K effort occurring at
    target_date. Every workout used is required to have workout.date <
    target_date - see _workouts_before.
    """
    prior_workouts = _workouts_before(all_workouts, target_date)
    recent_workouts = _recent_window(prior_workouts, target_date)

    features: dict[str, float | None] = {name: None for name in FEATURE_NAMES}

    features["recent_2k_pace"] = _most_recent_pace_for_distance(prior_workouts, target_date, TARGET_DISTANCE_M)
    features["recent_5k_pace"] = _most_recent_pace_for_distance(prior_workouts, target_date, REFERENCE_DISTANCES_M["5k"])
    features["recent_6k_pace"] = _most_recent_pace_for_distance(prior_workouts, target_date, REFERENCE_DISTANCES_M["6k"])
    features["recent_10k_pace"] = _most_recent_pace_for_distance(prior_workouts, target_date, REFERENCE_DISTANCES_M["10k"])

    if recent_workouts:
        watts_values = [w.avg_watts for w in recent_workouts]
        features["best_recent_watts"] = max(watts_values)
        features["avg_watts"] = sum(watts_values) / len(watts_values)
        features["avg_workout_duration_s"] = sum(w.total_duration_s for w in recent_workouts) / len(recent_workouts)
        features["avg_workout_distance_m"] = sum(w.total_distance_m for w in recent_workouts) / len(recent_workouts)

        hr_values = [w.avg_hr for w in recent_workouts if w.avg_hr is not None]
        if hr_values:
            features["avg_hr"] = sum(hr_values) / len(hr_values)
            features["max_hr"] = max(hr_values)

        spm_values = [w.avg_stroke_rate for w in recent_workouts if w.avg_stroke_rate is not None]
        if spm_values:
            features["avg_stroke_rate"] = sum(spm_values) / len(spm_values)

    # Workout-specific computed metrics (HR drift, EF, pacing CV, interval
    # decay) come from the single most recent prior workout where each is
    # available, since they're not simple aggregates.
    for workout in sorted(prior_workouts, key=lambda w: w.date, reverse=True):
        if all(
            features[k] is not None
            for k in ["hr_drift_pct", "efficiency_factor", "pacing_consistency_cv_pct", "interval_decay_slope"]
        ):
            break

        if features["efficiency_factor"] is None and workout.avg_watts and workout.avg_hr:
            ef_metrics, _ = compute_efficiency_factor({"avg_watts": workout.avg_watts, "avg_hr": workout.avg_hr})
            if ef_metrics is not None:
                features["efficiency_factor"] = ef_metrics["efficiency_factor"]

        if workout.has_splits and (
            features["hr_drift_pct"] is None
            or features["pacing_consistency_cv_pct"] is None
            or features["interval_decay_slope"] is None
        ):
            result = compute_workout_analytics(workout, athlete=athlete)
            if features["pacing_consistency_cv_pct"] is None:
                features["pacing_consistency_cv_pct"] = result["metrics"]["pacing"]["pacing_cv_pct"]
            if features["interval_decay_slope"] is None and result["metrics"]["intervals"] is not None:
                features["interval_decay_slope"] = result["metrics"]["intervals"]["decay"]["slope_watts_per_interval"]
            if features["hr_drift_pct"] is None and result["metrics"]["hr_drift"] is not None:
                features["hr_drift_pct"] = result["metrics"]["hr_drift"]["drift_pct"]

    reference_2k_watts = find_reference_2k_watts(athlete, prior_workouts)
    loads_by_workout = [
        (w.date, compute_workout_training_load(w, athlete, w.avg_hr, reference_2k_watts)["value"])
        for w in prior_workouts
    ]
    daily_series = build_daily_load_series(loads_by_workout)
    if daily_series:
        latest = daily_series[-1]
        features["recent_training_load"] = latest["daily_load"]
        features["training_load_7day"] = latest["rolling_7_day"]
        features["training_load_28day"] = latest["rolling_28_day"]

    features["athlete_weight_kg"] = athlete.weight_kg

    return features
