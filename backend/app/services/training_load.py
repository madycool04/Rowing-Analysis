"""
Training load (spec section 17).

Preferred method: Banister TRIMP, which needs resting HR, max HR, and a
workout's average HR. Falls back to duration x intensity-factor
(intensity estimated relative to a reference 2K effort) when HR data
isn't adequate. The fallback is always labeled as an analytical
estimate, never presented as equivalent precision to TRIMP.

IMPORTANT: training load (and any ACWR-style ratio derived from it) is
never presented as an injury-prediction metric anywhere in this module
or its API layer - it's descriptive training-volume information only.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from app.models.athlete import Athlete, Sex
from app.models.workout import Workout
from app.services.performance import _collect_efforts
from app.utils.pace import average_pace_per_500, watts_from_pace_per_500

ROLLING_WINDOWS = {"7_day": 7, "28_day": 28}


def banister_trimp(duration_min: float, avg_hr: float, resting_hr: int, max_hr: int, sex: Sex | None) -> float | None:
    if max_hr <= resting_hr:
        return None
    hr_ratio = (avg_hr - resting_hr) / (max_hr - resting_hr)
    hr_ratio = max(0.0, min(hr_ratio, 1.2))  # clamp - avg_hr occasionally exceeds max_hr in noisy data

    if sex == Sex.FEMALE:
        k, b = 0.86, 1.67
    else:
        # Default to the men's coefficients when sex is unset - this is a
        # known approximation, not a claim about the athlete.
        k, b = 0.64, 1.92

    return duration_min * hr_ratio * k * math.exp(b * hr_ratio)


def compute_workout_training_load(
    workout: Workout,
    athlete: Athlete,
    avg_hr: float | None,
    reference_2k_watts: float | None,
) -> dict:
    """
    Returns {"method": "trimp"|"fallback"|"unavailable", "value": float|None, "note": str}.
    """
    duration_min = workout.total_duration_s / 60.0

    can_use_trimp = (
        avg_hr is not None
        and athlete.resting_hr is not None
        and athlete.max_hr is not None
        and athlete.max_hr > athlete.resting_hr
    )
    if can_use_trimp:
        trimp = banister_trimp(duration_min, avg_hr, athlete.resting_hr, athlete.max_hr, athlete.sex)
        if trimp is not None:
            return {
                "method": "trimp",
                "value": round(trimp, 1),
                "note": "Banister TRIMP, computed from this workout's average heart rate.",
            }

    avg_pace = average_pace_per_500(workout.total_distance_m, workout.total_duration_s)
    avg_watts = watts_from_pace_per_500(avg_pace)

    if reference_2k_watts and reference_2k_watts > 0:
        intensity_factor = avg_watts / reference_2k_watts
        fallback_value = duration_min * intensity_factor
        return {
            "method": "fallback",
            "value": round(fallback_value, 1),
            "note": (
                "Analytical estimate: duration x intensity (relative to a recent 2K effort), used "
                "because heart-rate data or athlete HR profile wasn't sufficient for TRIMP."
            ),
        }

    return {
        "method": "unavailable",
        "value": None,
        "note": (
            "Training load could not be estimated - this requires either heart-rate data with a "
            "complete athlete HR profile, or a recent 2K effort to estimate relative intensity."
        ),
    }


def find_reference_2k_watts(athlete: Athlete, workouts: list[Workout]) -> float | None:
    """
    Used by the training-load fallback to estimate relative intensity
    (spec section 17). Prefers the athlete's stated 2K best; otherwise
    falls back to the fastest actual ~2000m effort found in their history
    (whole-workout or a single interval rep, same detection as PBs).
    """
    if athlete.best_2k_seconds:
        pace = average_pace_per_500(2000.0, athlete.best_2k_seconds)
        return watts_from_pace_per_500(pace)

    best_duration: float | None = None
    for workout in workouts:
        for effort in _collect_efforts(workout):
            if abs(effort.distance_m - 2000.0) / 2000.0 <= 0.03:
                if best_duration is None or effort.duration_s < best_duration:
                    best_duration = effort.duration_s

    if best_duration is None:
        return None
    pace = average_pace_per_500(2000.0, best_duration)
    return watts_from_pace_per_500(pace)


def _to_date(dt: datetime) -> date:
    return dt.date() if hasattr(dt, "date") else dt


def build_daily_load_series(loads_by_workout: list[tuple[datetime, float | None]]) -> list[dict]:
    """Aggregates per-workout loads into a daily series with 7-day and 28-day rolling sums."""
    daily: dict[date, float] = defaultdict(float)
    for workout_date, load in loads_by_workout:
        if load is None:
            continue
        daily[_to_date(workout_date)] += load

    if not daily:
        return []

    all_dates = sorted(daily.keys())
    start, end = all_dates[0], all_dates[-1]

    date_list = []
    d = start
    while d <= end:
        date_list.append(d)
        d += timedelta(days=1)

    series = []
    for d in date_list:
        day_load = round(daily.get(d, 0.0), 1)
        window_7 = sum(daily.get(d - timedelta(days=i), 0.0) for i in range(7))
        window_28 = sum(daily.get(d - timedelta(days=i), 0.0) for i in range(28))
        acute_avg = window_7 / 7.0
        chronic_avg = window_28 / 28.0
        acwr = round(acute_avg / chronic_avg, 2) if chronic_avg > 0 else None
        series.append(
            {
                "date": d.isoformat(),
                "daily_load": day_load,
                "rolling_7_day": round(window_7, 1),
                "rolling_28_day": round(window_28, 1),
                # Acute:chronic workload ratio - descriptive training-volume
                # information ONLY. Per spec section 17, this is NEVER
                # presented as an injury-prediction metric anywhere in
                # this codebase, despite that being a common (and
                # scientifically contested) use of ACWR elsewhere.
                "acwr": acwr,
            }
        )
    return series
