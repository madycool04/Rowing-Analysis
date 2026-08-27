"""
Live 2K prediction (spec sections 24-25).

Model selection is NOT hardcoded to "the fanciest available model" - it
uses whatever Phase 8's walk-forward validation found to have the lowest
MAE for this athlete, which may well be a baseline. The interval is a
split-conformal margin calibrated from the SAME walk-forward residuals
used to pick the method, so a method that validated poorly naturally
produces a wider (more honest) interval, not a falsely tight one.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.models.athlete import Athlete
from app.models.prediction import Prediction
from app.models.workout import Workout
from app.services.ml.baselines import TARGET_DISTANCE_M, pauls_law_2k_baseline, previous_2k_baseline
from app.services.ml.features import build_feature_vector
from app.services.ml.train import (
    MIN_HISTORICAL_2K_FOR_RELIABLE_ML,
    _MODEL_FITTERS,
    _find_2k_targets,
    _prepare_matrix,
    _run_folds,
)

MIN_CALIBRATION_SAMPLES = 3
CONFORMAL_ALPHA = 0.10  # targets ~90% coverage
HIGH_CONFIDENCE_THRESHOLD = 10

# Features compared for the plain-language explanation (spec section 25).
# Each entry: (feature_key, display_label, "lower_is_better" | "higher_is_better" | "neutral")
EXPLANATION_FEATURES = [
    ("recent_5k_pace", "Recent 5K performance", "lower_is_better"),
    ("recent_2k_pace", "Recent 2K performance", "lower_is_better"),
    ("training_load_7day", "Training load", "neutral"),
    ("efficiency_factor", "Efficiency factor", "higher_is_better"),
]


def _conformal_margin(abs_errors: list[float]) -> float | None:
    """Split-conformal margin: the ceil((k+1)(1-alpha))-th order statistic of calibration errors."""
    k = len(abs_errors)
    if k < MIN_CALIBRATION_SAMPLES:
        return None
    sorted_errors = sorted(abs_errors)
    q_index = min(math.ceil((k + 1) * (1 - CONFORMAL_ALPHA)) - 1, k - 1)
    return sorted_errors[q_index]


def _confidence_label(n_historical_2k: int, calibration_samples: int) -> str:
    if n_historical_2k < MIN_HISTORICAL_2K_FOR_RELIABLE_ML or calibration_samples < MIN_CALIBRATION_SAMPLES:
        return "low"
    if n_historical_2k < HIGH_CONFIDENCE_THRESHOLD:
        return "moderate"
    return "high"


def _fit_ml_prediction(method_name: str, athlete: Athlete, all_workouts: list[Workout], current_features: dict) -> float | None:
    """Refits `method_name` on every historical 2K's own leakage-safe features, then predicts `current_features`."""
    targets = _find_2k_targets(all_workouts)
    training_rows = [
        (build_feature_vector(athlete, all_workouts, target_date), actual_time_s)
        for target_date, actual_time_s, _wid in targets
    ]
    if not training_rows:
        return None
    prepared = _prepare_matrix(training_rows, current_features)
    if prepared is None:
        return None
    x_train, y_train, x_current, _used = prepared
    return _MODEL_FITTERS[method_name](x_train, y_train, x_current)


def _build_explanation(current_features: dict, previous_features: dict | None) -> list[dict]:
    if previous_features is None:
        return []

    factors = []
    for key, label, direction in EXPLANATION_FEATURES:
        cur = current_features.get(key)
        prev = previous_features.get(key)
        if cur is None or prev is None:
            continue

        delta = cur - prev
        if abs(delta) < 1e-9:
            trend = "unchanged"
        elif direction == "lower_is_better":
            trend = "positive" if delta < 0 else "negative"
        elif direction == "higher_is_better":
            trend = "positive" if delta > 0 else "negative"
        else:
            trend = "up" if delta > 0 else "down"

        factors.append({"factor": label, "trend": trend})

    return factors


def predict_2k(athlete: Athlete, all_workouts: list[Workout], db=None, now: datetime | None = None) -> dict:
    """
    Returns a dict describing the current 2K prediction. If `db` (a
    SQLAlchemy session) is provided, persists a Prediction row and
    includes an explanation comparing against the athlete's previous
    stored prediction, if one exists.
    """
    now = now or datetime.now(timezone.utc)

    targets = _find_2k_targets(all_workouts)
    n_historical_2k = len(targets)

    prev_baseline = previous_2k_baseline(all_workouts, before_date=now)
    paul_baseline = pauls_law_2k_baseline(all_workouts, before_date=now)

    if n_historical_2k == 0 and not prev_baseline["available"] and not paul_baseline["available"]:
        return {
            "available": False,
            "reason": (
                "No 2K, 5K, 6K, or 10K efforts found yet - log a qualifying workout to get a prediction."
            ),
        }

    baseline_errors, model_errors, _n = _run_folds(athlete, all_workouts)
    all_errors = {**baseline_errors, **model_errors}
    available_methods = {name: errs for name, errs in all_errors.items() if errs}
    best_method = (
        min(available_methods, key=lambda k: sum(available_methods[k]) / len(available_methods[k]))
        if available_methods
        else None
    )

    current_features = build_feature_vector(athlete, all_workouts, target_date=now)

    predicted_time_s: float | None = None
    method_used: str | None = None

    def _try_baseline(name: str) -> bool:
        nonlocal predicted_time_s, method_used
        baseline = prev_baseline if name == "previous_2k" else paul_baseline
        if baseline["available"]:
            predicted_time_s = baseline["predicted_time_s"]
            method_used = name
            return True
        return False

    if best_method in ("previous_2k", "pauls_law"):
        _try_baseline(best_method)
    elif best_method is not None:
        ml_prediction = _fit_ml_prediction(best_method, athlete, all_workouts, current_features)
        if ml_prediction is not None:
            predicted_time_s = ml_prediction
            method_used = best_method

    if predicted_time_s is None:
        # Fall back through baselines in preference order if the chosen
        # method couldn't actually produce a live prediction.
        if not _try_baseline("previous_2k"):
            _try_baseline("pauls_law")

    if predicted_time_s is None:
        return {
            "available": False,
            "reason": "Not enough data to generate any prediction yet.",
        }

    calibration_errors = all_errors.get(method_used, [])
    margin = _conformal_margin(calibration_errors)
    confidence = _confidence_label(n_historical_2k, len(calibration_errors))

    lower_bound = round(predicted_time_s - margin, 1) if margin is not None else None
    upper_bound = round(predicted_time_s + margin, 1) if margin is not None else None

    result = {
        "available": True,
        "predicted_time_s": round(predicted_time_s, 1),
        "target_distance_m": TARGET_DISTANCE_M,
        "lower_bound_s": lower_bound,
        "upper_bound_s": upper_bound,
        "confidence": confidence,
        "method_used": method_used,
        "n_historical_2k_tests": n_historical_2k,
        "sufficient_data_for_ml": n_historical_2k >= MIN_HISTORICAL_2K_FOR_RELIABLE_ML,
        "note": (
            "This is a model estimate, not a guaranteed performance. "
            + (
                "Confidence is low - only a few historical efforts are available, so treat this as a "
                "rough estimate."
                if confidence == "low"
                else "The range reflects typical error observed when this method predicted your past 2K efforts."
            )
        ),
    }

    if db is not None:
        previous_prediction = (
            db.query(Prediction)
            .filter(Prediction.athlete_id == athlete.id, Prediction.target_distance_m == TARGET_DISTANCE_M)
            .order_by(Prediction.prediction_date.desc())
            .first()
        )
        previous_features = previous_prediction.features_used if previous_prediction else None
        previous_predicted_time = previous_prediction.predicted_time_s if previous_prediction else None

        result["contributing_factors"] = _build_explanation(current_features, previous_features)
        result["change_vs_previous_s"] = (
            round(predicted_time_s - previous_predicted_time, 1) if previous_predicted_time is not None else None
        )

        prediction_row = Prediction(
            athlete_id=athlete.id,
            model_name=method_used,
            model_version="v1",
            prediction_date=now,
            target_distance_m=TARGET_DISTANCE_M,
            predicted_time_s=result["predicted_time_s"],
            lower_bound_s=lower_bound,
            upper_bound_s=upper_bound,
            confidence=confidence,
            features_used=current_features,
        )
        db.add(prediction_row)
        db.commit()
    else:
        result["contributing_factors"] = []
        result["change_vs_previous_s"] = None

    return result
