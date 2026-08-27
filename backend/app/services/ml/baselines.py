"""
Non-ML 2K prediction baselines (spec section 20).

These exist for two reasons: they're useful predictions in their own
right for rowers, and every ML model trained later (Phase 9) must beat
them before it's presented as "better" - see the walk-forward validation
in train.py.
"""

from __future__ import annotations

from datetime import datetime

from app.services.performance import Effort, _collect_efforts

# Paul's Law: an empirical rowing heuristic (not a physical law) relating
# race times across distances via T2 = T1 * (D2/D1)^EXPONENT. Commonly
# cited with an exponent around 1.06. This is an approximation, most
# reliable when extrapolating from a nearby distance (5K is a smaller
# extrapolation to 2K than 10K is).
PAULS_LAW_EXPONENT = 1.06
TARGET_DISTANCE_M = 2000.0
REFERENCE_DISTANCES_M = {"5k": 5000.0, "6k": 6000.0, "10k": 10000.0}
DISTANCE_TOLERANCE_PCT = 0.03


def pauls_law_predict(known_time_s: float, known_distance_m: float, target_distance_m: float = TARGET_DISTANCE_M) -> float:
    """T2 = T1 * (D2/D1)^1.06 - see module docstring. Both distances must be positive."""
    if known_time_s <= 0 or known_distance_m <= 0 or target_distance_m <= 0:
        raise ValueError("times and distances must be positive")
    return known_time_s * (target_distance_m / known_distance_m) ** PAULS_LAW_EXPONENT


def _qualifying_efforts_before(
    workouts: list, target_m: float, before_date: datetime | None
) -> list[Effort]:
    efforts: list[Effort] = []
    for workout in workouts:
        if before_date is not None and workout.date >= before_date:
            continue
        for effort in _collect_efforts(workout):
            if abs(effort.distance_m - target_m) / target_m <= DISTANCE_TOLERANCE_PCT:
                efforts.append(effort)
    return efforts


def previous_2k_baseline(workouts: list, before_date: datetime | None = None) -> dict:
    """
    Simplest baseline: the most recent actual 2K effort before the
    target date. Requires at least one prior 2K.
    """
    efforts = _qualifying_efforts_before(workouts, TARGET_DISTANCE_M, before_date)
    if not efforts:
        return {
            "available": False,
            "predicted_time_s": None,
            "reason": "No previous 2K effort found.",
            "source": None,
        }

    most_recent = max(efforts, key=lambda e: e.date)
    return {
        "available": True,
        "predicted_time_s": round(most_recent.duration_s, 1),
        "reason": None,
        "source": {"workout_id": most_recent.workout_id, "date": most_recent.date.isoformat()},
    }


def pauls_law_2k_baseline(workouts: list, before_date: datetime | None = None) -> dict:
    """
    Predicts 2K time from the athlete's most recent 5K/6K/10K effort
    before the target date via Paul's Law. Prefers the closest reference
    distance (5K) when multiple are available on the same most-recent
    date; otherwise just uses whichever reference effort is most recent.
    """
    candidates: list[tuple[Effort, float]] = []  # (effort, reference_distance_m)
    for label, dist_m in REFERENCE_DISTANCES_M.items():
        for effort in _qualifying_efforts_before(workouts, dist_m, before_date):
            candidates.append((effort, dist_m))

    if not candidates:
        return {
            "available": False,
            "predicted_time_s": None,
            "reason": "No 5K, 6K, or 10K effort found to extrapolate from.",
            "source": None,
        }

    # Most recent first; prefer the smaller reference distance (5K) as a tiebreaker
    # since it's a smaller extrapolation gap to 2K.
    candidates.sort(key=lambda c: (c[0].date, -c[1]), reverse=True)
    best_effort, ref_distance = candidates[0]

    predicted = pauls_law_predict(best_effort.duration_s, ref_distance, TARGET_DISTANCE_M)
    return {
        "available": True,
        "predicted_time_s": round(predicted, 1),
        "reason": None,
        "source": {
            "workout_id": best_effort.workout_id,
            "date": best_effort.date.isoformat(),
            "reference_distance_m": ref_distance,
        },
        "note": (
            "Paul's Law is an empirical heuristic (T2 = T1 x (D2/D1)^1.06), not a precise "
            "physiological prediction - accuracy depends on how well your pacing profile at the "
            "reference distance matches a 2K effort."
        ),
    }
