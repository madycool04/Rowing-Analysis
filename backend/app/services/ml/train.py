"""
Walk-forward validation for 2K prediction (spec section 22).

CRITICAL: this is chronological expanding-window validation, never a
random train/test split. For each historical 2K test, in date order:
  1. Build its feature vector using ONLY workouts strictly before it.
  2. Get baseline predictions (previous-2K, Paul's Law) using only prior data.
  3. If enough earlier 2Ks exist, fit each ML model on those earlier 2Ks'
     own (equally leakage-safe) feature vectors and predict this one.
  4. Record errors, then add this 2K to the training pool for future folds.

Every model is compared against both baselines. If a model doesn't beat
them, this module does not hide that fact - see `best_method` in the
returned report, which is chosen purely by lowest MAE, not by any
preference for ML over baselines (spec section 22: "If ML does not beat
the baselines, do not pretend that ML is better").

Small-dataset protection (spec section 23): fewer than 5 historical 2K
tests means `sufficient_data_for_ml` is False, signaling callers (Phase 9's
prediction endpoint) to not present an athlete-specific ML prediction as
reliable, regardless of what the raw numbers show.
"""

from __future__ import annotations

import math

from app.models.athlete import Athlete
from app.models.workout import Workout
from app.services.ml.baselines import TARGET_DISTANCE_M, pauls_law_2k_baseline, previous_2k_baseline
from app.services.ml.features import FEATURE_NAMES, build_feature_vector
from app.services.performance import _collect_efforts

MIN_TRAINING_ROWS = {"ridge": 2, "random_forest": 5, "xgboost": 5}
MIN_HISTORICAL_2K_FOR_RELIABLE_ML = 5
DISTANCE_TOLERANCE_PCT = 0.03


def _find_2k_targets(workouts: list[Workout]) -> list[tuple]:
    """Returns [(date, duration_s, workout_id), ...] for every qualifying 2K effort, chronological."""
    targets = []
    for workout in workouts:
        for effort in _collect_efforts(workout):
            if abs(effort.distance_m - TARGET_DISTANCE_M) / TARGET_DISTANCE_M <= DISTANCE_TOLERANCE_PCT:
                targets.append((effort.date, effort.duration_s, effort.workout_id))
    targets.sort(key=lambda t: t[0])
    return targets


def _prepare_matrix(training_rows: list[tuple[dict, float]], current_features: dict):
    """
    Builds (X_train, y_train, x_current, feature_names_used) for sklearn,
    imputing missing values with the training-set column mean. Features
    with zero coverage in the training set are dropped rather than
    imputed with an arbitrary constant.
    """
    usable = [
        name for name in FEATURE_NAMES if any(row[0].get(name) is not None for row in training_rows)
    ]
    if not usable:
        return None

    means: dict[str, float] = {}
    for name in usable:
        values = [row[0][name] for row in training_rows if row[0].get(name) is not None]
        means[name] = sum(values) / len(values) if values else 0.0

    x_train = [[(feats.get(name) if feats.get(name) is not None else means[name]) for name in usable] for feats, _ in training_rows]
    y_train = [actual for _, actual in training_rows]
    x_current = [current_features.get(name) if current_features.get(name) is not None else means[name] for name in usable]

    return x_train, y_train, x_current, usable


def _fit_predict_ridge(x_train, y_train, x_current) -> float | None:
    try:
        from sklearn.linear_model import Ridge

        model = Ridge(alpha=1.0)
        model.fit(x_train, y_train)
        return float(model.predict([x_current])[0])
    except Exception:  # noqa: BLE001 - any fitting failure just means this model is unavailable for this fold
        return None


def _fit_predict_random_forest(x_train, y_train, x_current) -> float | None:
    try:
        from sklearn.ensemble import RandomForestRegressor

        model = RandomForestRegressor(n_estimators=100, max_depth=4, random_state=42)
        model.fit(x_train, y_train)
        return float(model.predict([x_current])[0])
    except Exception:  # noqa: BLE001
        return None


def _fit_predict_xgboost(x_train, y_train, x_current) -> float | None:
    try:
        from xgboost import XGBRegressor

        model = XGBRegressor(n_estimators=50, max_depth=3, random_state=42, verbosity=0)
        model.fit(x_train, y_train)
        return float(model.predict([x_current])[0])
    except Exception:  # noqa: BLE001
        return None


_MODEL_FITTERS = {
    "ridge": _fit_predict_ridge,
    "random_forest": _fit_predict_random_forest,
    "xgboost": _fit_predict_xgboost,
}


def _summarize_errors(errors: list[float]) -> dict:
    if not errors:
        return {"available": False, "mae_s": None, "rmse_s": None, "n_folds": 0}
    mae = sum(errors) / len(errors)
    rmse = math.sqrt(sum(e**2 for e in errors) / len(errors))
    return {"available": True, "mae_s": round(mae, 2), "rmse_s": round(rmse, 2), "n_folds": len(errors)}


def _run_folds(athlete: Athlete, all_workouts: list[Workout]) -> tuple[dict[str, list[float]], dict[str, list[float]], int]:
    """
    Runs the chronological expanding-window walk-forward loop once and
    returns the raw absolute-error lists per baseline/model, plus the
    number of folds evaluated. Shared by walk_forward_validate() (which
    summarizes these into MAE/RMSE) and predictor.py (which needs the
    raw list for a chosen method to calibrate a conformal interval).
    """
    targets = _find_2k_targets(all_workouts)

    baseline_errors: dict[str, list[float]] = {"previous_2k": [], "pauls_law": []}
    model_errors: dict[str, list[float]] = {name: [] for name in _MODEL_FITTERS}
    training_rows: list[tuple[dict, float]] = []

    for target_date, actual_time_s, _workout_id in targets:
        prev = previous_2k_baseline(all_workouts, before_date=target_date)
        if prev["available"]:
            baseline_errors["previous_2k"].append(abs(prev["predicted_time_s"] - actual_time_s))

        paul = pauls_law_2k_baseline(all_workouts, before_date=target_date)
        if paul["available"]:
            baseline_errors["pauls_law"].append(abs(paul["predicted_time_s"] - actual_time_s))

        current_features = build_feature_vector(athlete, all_workouts, target_date)

        for model_name, fitter in _MODEL_FITTERS.items():
            if len(training_rows) < MIN_TRAINING_ROWS[model_name]:
                continue
            prepared = _prepare_matrix(training_rows, current_features)
            if prepared is None:
                continue
            x_train, y_train, x_current, _used = prepared
            prediction = fitter(x_train, y_train, x_current)
            if prediction is not None:
                model_errors[model_name].append(abs(prediction - actual_time_s))

        # This 2K becomes a training example for every subsequent (later) fold.
        training_rows.append((current_features, actual_time_s))

    return baseline_errors, model_errors, len(targets)


def walk_forward_validate(athlete: Athlete, all_workouts: list[Workout]) -> dict:
    baseline_errors, model_errors, n_targets = _run_folds(athlete, all_workouts)

    if n_targets == 0:
        return {
            "available": False,
            "reason": "No historical 2K efforts found to validate against.",
            "n_historical_2k_tests": 0,
            "sufficient_data_for_ml": False,
        }

    baseline_summary = {name: _summarize_errors(errs) for name, errs in baseline_errors.items()}
    model_summary = {name: _summarize_errors(errs) for name, errs in model_errors.items()}

    all_candidates = {**baseline_summary, **model_summary}
    available_candidates = {k: v for k, v in all_candidates.items() if v["available"]}
    best_method = min(available_candidates, key=lambda k: available_candidates[k]["mae_s"]) if available_candidates else None

    return {
        "available": True,
        "n_historical_2k_tests": n_targets,
        "n_folds_evaluated": n_targets,
        "sufficient_data_for_ml": n_targets >= MIN_HISTORICAL_2K_FOR_RELIABLE_ML,
        "baselines": baseline_summary,
        "models": model_summary,
        "best_method": best_method,
        "note": (
            "Errors are from chronological walk-forward validation (each historical 2K predicted "
            "using only data available before it), not a random train/test split. A model is only "
            "meaningfully validated once several folds have been evaluated - early folds in an "
            "athlete's history are inherently noisier."
        ),
    }
