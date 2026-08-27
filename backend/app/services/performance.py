"""
Personal bests (spec section 18) and performance trends (spec section 19).

PB detection scans both whole-workout distances (continuous pieces) and
individual WORK segments (so a rep within a 4x1K or 5x500m session can
count toward the 1K/500m PB) - this follows naturally from the
Workout -> Segment -> Split model without any special-cased logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models.segment import SegmentType
from app.models.workout import Workout
from app.utils.pace import average_pace_per_500, format_pace, watts_from_pace_per_500

# Standard distances tracked for PBs, with a tolerance band so that a
# real-world 2005m piece still counts as a "2K" effort.
STANDARD_DISTANCES: dict[str, float] = {
    "500m": 500.0,
    "1k": 1000.0,
    "2k": 2000.0,
    "5k": 5000.0,
    "6k": 6000.0,
    "10k": 10000.0,
}
DISTANCE_TOLERANCE_PCT = 0.03


@dataclass
class Effort:
    distance_m: float
    duration_s: float
    date: datetime
    workout_id: int
    is_whole_workout: bool


def _collect_efforts(workout: Workout) -> list[Effort]:
    efforts = [
        Effort(
            distance_m=workout.total_distance_m,
            duration_s=workout.total_duration_s,
            date=workout.date,
            workout_id=workout.id,
            is_whole_workout=True,
        )
    ]

    # A continuous workout has exactly one WORK segment spanning the
    # entire workout - that segment IS the whole-workout effort already
    # added above, not a second, distinct one. Only treat WORK segments
    # as their own efforts when there's more than one segment (intervals,
    # or a mixed warmup/intervals/cooldown session), where each rep is a
    # genuinely smaller, separate effort worth its own PB/target
    # consideration.
    if len(workout.segments) <= 1:
        return efforts

    for segment in workout.segments:
        if segment.type == SegmentType.WORK and segment.distance_m > 0 and segment.duration_s > 0:
            efforts.append(
                Effort(
                    distance_m=segment.distance_m,
                    duration_s=segment.duration_s,
                    date=workout.date,
                    workout_id=workout.id,
                    is_whole_workout=False,
                )
            )
    return efforts


def _matches_distance(effort_distance_m: float, target_m: float) -> bool:
    return abs(effort_distance_m - target_m) / target_m <= DISTANCE_TOLERANCE_PCT


def compute_personal_bests(workouts: list[Workout]) -> dict[str, dict]:
    """
    Returns {distance_label: {current: {...}, previous: {...}|None, improvement_s: float|None}}
    for every standard distance that has at least one qualifying effort.
    """
    results: dict[str, dict] = {}

    for label, target_m in STANDARD_DISTANCES.items():
        qualifying: list[Effort] = []
        for workout in workouts:
            for effort in _collect_efforts(workout):
                if _matches_distance(effort.distance_m, target_m):
                    qualifying.append(effort)

        if not qualifying:
            continue

        # Sort by date so "previous PB" means the best result *before* the current best was set.
        qualifying.sort(key=lambda e: e.date)

        best_so_far: Effort | None = None
        previous_best: Effort | None = None
        for effort in qualifying:
            if best_so_far is None or effort.duration_s < best_so_far.duration_s:
                previous_best = best_so_far
                best_so_far = effort

        assert best_so_far is not None  # qualifying is non-empty

        def _describe(effort: Effort) -> dict:
            pace = average_pace_per_500(effort.distance_m, effort.duration_s)
            return {
                "distance_m": round(effort.distance_m, 1),
                "duration_s": round(effort.duration_s, 1),
                "pace_display": format_pace(pace),
                "avg_watts": round(watts_from_pace_per_500(pace), 1),
                "date": effort.date.isoformat() if effort.date else None,
                "workout_id": effort.workout_id,
            }

        improvement_s = None
        if previous_best is not None:
            improvement_s = round(previous_best.duration_s - best_so_far.duration_s, 1)

        results[label] = {
            "current": _describe(best_so_far),
            "previous": _describe(previous_best) if previous_best else None,
            "improvement_s": improvement_s,
        }

    return results


def build_progression_series(workouts: list[Workout], target_label: str) -> list[dict]:
    """
    Chronological series of every qualifying effort at a given standard
    distance (spec section 19: "2K performance over time", etc.) - not
    just the running PB, so the frontend can plot every attempt.
    """
    target_m = STANDARD_DISTANCES.get(target_label)
    if target_m is None:
        return []

    points = []
    for workout in workouts:
        for effort in _collect_efforts(workout):
            if _matches_distance(effort.distance_m, target_m):
                pace = average_pace_per_500(effort.distance_m, effort.duration_s)
                points.append(
                    {
                        "date": effort.date.isoformat() if effort.date else None,
                        "duration_s": round(effort.duration_s, 1),
                        "pace_display": format_pace(pace),
                        "avg_watts": round(watts_from_pace_per_500(pace), 1),
                        "workout_id": effort.workout_id,
                    }
                )
    points.sort(key=lambda p: p["date"] or "")
    return points
