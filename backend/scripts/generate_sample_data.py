"""
Generates realistic synthetic rowing workouts for development, testing,
and demos (spec section 34).

Usage (from backend/, with PYTHONPATH=. or via `python -m scripts.generate_sample_data`):

    python scripts/generate_sample_data.py --email demo@example.com --password demo12345

Creates the user/athlete if they don't already exist, then generates ~10
weeks of varied workouts: 2K/5K/6K/10K tests, 30-min steady state,
4x1K, 5x500m, 3x2K, a threshold piece, and a warmup+intervals+cooldown
session - covering even, positive-split, negative-split, fly-and-die,
and interval-fade pacing patterns.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal, import_all_models  # noqa: E402
from app.models.athlete import Athlete  # noqa: E402
from app.models.segment import SegmentType  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.workout import WorkoutCategory, WorkoutSource  # noqa: E402
from app.services.csv_parser import ParsedSegment, ParsedSplit, ParsedWorkout, _weighted_hr_and_spm_from_segments  # noqa: E402
from app.services.workout_import import persist_parsed_workout  # noqa: E402
from app.utils.pace import watts_from_pace_per_500  # noqa: E402

import_all_models()

RNG = random.Random(42)

# Pacing multipliers applied to a base 500m pace, one per split index in a
# 4-split piece; interpolated for other split counts. >1.0 = slower.
PACING_PATTERNS: dict[str, list[float]] = {
    "even": [1.00, 1.00, 1.00, 1.00],
    "positive_split": [0.985, 0.995, 1.005, 1.02],   # fades over the piece
    "negative_split": [1.02, 1.005, 0.995, 0.98],    # builds through the piece
    "fly_and_die": [0.96, 0.98, 1.03, 1.06],          # fast start, heavy fade
}


def _interpolate_pattern(pattern: list[float], n_splits: int) -> list[float]:
    if n_splits == len(pattern):
        return pattern
    # Simple linear resample so any split count gets a sensibly-shaped curve.
    result = []
    for i in range(n_splits):
        pos = i / max(n_splits - 1, 1) * (len(pattern) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(pattern) - 1)
        frac = pos - lo
        result.append(pattern[lo] * (1 - frac) + pattern[hi] * frac)
    return result


def _hr_for_intensity(intensity: float, resting_hr: int, max_hr: int) -> int:
    """intensity in [0,1] roughly maps effort to %HRR (Karvonen-style), plus noise."""
    hrr = max_hr - resting_hr
    hr = resting_hr + hrr * intensity
    return int(round(hr + RNG.uniform(-2, 2)))


def _spm_for_pace(pace_s_per_500: float, base_spm: float) -> float:
    return round(base_spm + RNG.uniform(-0.5, 0.5), 1)


def _calories_for(watts: float, duration_s: float) -> float:
    # Rough approximation, adequate for demo/synthetic data only.
    return round(watts * duration_s * 0.0028, 1)


def _build_continuous(
    total_distance_m: float,
    avg_pace_s500: float,
    pattern_key: str,
    title: str,
    date: datetime,
    resting_hr: int,
    max_hr: int,
    base_intensity: float,
    base_spm: float,
    split_size_m: float = 500.0,
) -> ParsedWorkout:
    n_splits = max(int(round(total_distance_m / split_size_m)), 1)
    multipliers = _interpolate_pattern(PACING_PATTERNS[pattern_key], n_splits)

    splits: list[ParsedSplit] = []
    cumulative_time = 0.0
    for i, mult in enumerate(multipliers):
        split_distance = split_size_m
        split_pace = avg_pace_s500 * mult
        split_duration = split_pace * (split_distance / 500.0)
        watts = watts_from_pace_per_500(split_pace)
        hr = _hr_for_intensity(base_intensity * (2 - mult), resting_hr, max_hr)
        spm = _spm_for_pace(split_pace, base_spm)
        calories = _calories_for(watts, split_duration)

        splits.append(
            ParsedSplit(
                ordinal=i,
                distance_m=split_distance,
                elapsed_time_s=split_duration,
                pace_s_per_500=split_pace,
                watts=watts,
                stroke_rate=spm,
                heart_rate=hr,
                calories=calories,
            )
        )
        cumulative_time += split_duration

    segment = ParsedSegment(
        ordinal=0,
        type=SegmentType.WORK,
        start_time_s=0.0,
        duration_s=cumulative_time,
        distance_m=total_distance_m,
        splits=splits,
    )
    avg_hr, avg_spm = _weighted_hr_and_spm_from_segments([segment])

    return ParsedWorkout(
        source=WorkoutSource.GENERATED_SAMPLE,
        category=WorkoutCategory.CONTINUOUS,
        title=title,
        date=date,
        total_distance_m=total_distance_m,
        total_duration_s=cumulative_time,
        has_hr=True,
        hr_coverage_pct=100.0,
        has_splits=True,
        split_granularity="per_split",
        has_power=True,
        has_distance=True,
        has_stroke_rate=True,
        avg_hr=avg_hr,
        avg_stroke_rate=avg_spm,
        segments=[segment],
    )


def _build_intervals(
    n_reps: int,
    rep_distance_m: float,
    rest_duration_s: float,
    avg_pace_s500: float,
    title: str,
    date: datetime,
    resting_hr: int,
    max_hr: int,
    base_intensity: float,
    base_spm: float,
    decay_per_rep: float = 0.006,
) -> ParsedWorkout:
    """Builds an interval workout with a gentle fade across reps (spec: interval decay)."""
    segments: list[ParsedSegment] = []
    cumulative_time = 0.0
    total_distance = 0.0

    for rep in range(n_reps):
        rep_pace = avg_pace_s500 * (1 + decay_per_rep * rep) * (1 + RNG.uniform(-0.01, 0.01))
        rep_duration = rep_pace * (rep_distance_m / 500.0)
        watts = watts_from_pace_per_500(rep_pace)
        hr = _hr_for_intensity(base_intensity + 0.02 * rep, resting_hr, max_hr)
        spm = _spm_for_pace(rep_pace, base_spm)
        calories = _calories_for(watts, rep_duration)

        work_segment = ParsedSegment(
            ordinal=len(segments),
            type=SegmentType.WORK,
            start_time_s=cumulative_time,
            duration_s=rep_duration,
            distance_m=rep_distance_m,
            splits=[
                ParsedSplit(
                    ordinal=0,
                    distance_m=rep_distance_m,
                    elapsed_time_s=rep_duration,
                    pace_s_per_500=rep_pace,
                    watts=watts,
                    stroke_rate=spm,
                    heart_rate=hr,
                    calories=calories,
                )
            ],
        )
        segments.append(work_segment)
        cumulative_time += rep_duration
        total_distance += rep_distance_m

        if rep < n_reps - 1:
            rest_segment = ParsedSegment(
                ordinal=len(segments),
                type=SegmentType.REST,
                start_time_s=cumulative_time,
                duration_s=rest_duration_s,
                distance_m=0.0,
                splits=[],
            )
            segments.append(rest_segment)
            cumulative_time += rest_duration_s

    avg_hr, avg_spm = _weighted_hr_and_spm_from_segments(segments)

    return ParsedWorkout(
        source=WorkoutSource.GENERATED_SAMPLE,
        category=WorkoutCategory.INTERVAL,
        title=title,
        date=date,
        total_distance_m=total_distance,
        total_duration_s=cumulative_time,
        has_hr=True,
        hr_coverage_pct=100.0,
        has_splits=True,
        split_granularity="interval",
        has_power=True,
        has_distance=True,
        has_stroke_rate=True,
        avg_hr=avg_hr,
        avg_stroke_rate=avg_spm,
        segments=segments,
    )


def _build_mixed_warmup_intervals_cooldown(
    avg_pace_s500: float,
    title: str,
    date: datetime,
    resting_hr: int,
    max_hr: int,
) -> ParsedWorkout:
    segments: list[ParsedSegment] = []
    cumulative_time = 0.0
    total_distance = 0.0

    # Warmup: 10 min easy
    warmup_pace = avg_pace_s500 * 1.18
    warmup_distance = 2000.0 * (500.0 / warmup_pace) / 4  # rough distance for ~10min at this pace
    warmup_duration = warmup_pace * (warmup_distance / 500.0)
    segments.append(
        ParsedSegment(
            ordinal=0,
            type=SegmentType.WARMUP,
            start_time_s=0.0,
            duration_s=warmup_duration,
            distance_m=warmup_distance,
            splits=[],
        )
    )
    cumulative_time += warmup_duration
    total_distance += warmup_distance

    # 4 x 500m intervals w/ 90s rest, nested inside the mixed workout
    for rep in range(4):
        rep_pace = avg_pace_s500 * 0.97 * (1 + 0.008 * rep)
        rep_duration = rep_pace * (500.0 / 500.0)
        watts = watts_from_pace_per_500(rep_pace)
        hr = _hr_for_intensity(0.85 + 0.02 * rep, resting_hr, max_hr)
        spm = _spm_for_pace(rep_pace, 30.0)
        segments.append(
            ParsedSegment(
                ordinal=len(segments),
                type=SegmentType.WORK,
                start_time_s=cumulative_time,
                duration_s=rep_duration,
                distance_m=500.0,
                splits=[
                    ParsedSplit(
                        ordinal=0,
                        distance_m=500.0,
                        elapsed_time_s=rep_duration,
                        pace_s_per_500=rep_pace,
                        watts=watts,
                        stroke_rate=spm,
                        heart_rate=hr,
                        calories=_calories_for(watts, rep_duration),
                    )
                ],
            )
        )
        cumulative_time += rep_duration
        total_distance += 500.0

        if rep < 3:
            segments.append(
                ParsedSegment(
                    ordinal=len(segments),
                    type=SegmentType.REST,
                    start_time_s=cumulative_time,
                    duration_s=90.0,
                    distance_m=0.0,
                    splits=[],
                )
            )
            cumulative_time += 90.0

    # Cooldown: 5 min easy
    cooldown_pace = avg_pace_s500 * 1.22
    cooldown_distance = 2000.0 * (500.0 / cooldown_pace) / 8
    cooldown_duration = cooldown_pace * (cooldown_distance / 500.0)
    segments.append(
        ParsedSegment(
            ordinal=len(segments),
            type=SegmentType.COOLDOWN,
            start_time_s=cumulative_time,
            duration_s=cooldown_duration,
            distance_m=cooldown_distance,
            splits=[],
        )
    )
    cumulative_time += cooldown_duration
    total_distance += cooldown_distance

    avg_hr, avg_spm = _weighted_hr_and_spm_from_segments(segments)

    return ParsedWorkout(
        source=WorkoutSource.GENERATED_SAMPLE,
        category=WorkoutCategory.MIXED,
        title=title,
        date=date,
        total_distance_m=total_distance,
        total_duration_s=cumulative_time,
        has_hr=True,
        hr_coverage_pct=57.0,  # only the WORK segments have per-split HR in this synthetic set
        has_splits=True,
        split_granularity="interval",
        has_power=True,
        has_distance=True,
        has_stroke_rate=True,
        avg_hr=avg_hr,
        avg_stroke_rate=avg_spm,
        segments=segments,
    )


def generate_workouts_for_athlete(base_2k_seconds: float, resting_hr: int, max_hr: int) -> list[ParsedWorkout]:
    base_pace = base_2k_seconds / 4.0  # seconds per 500m at 2K test pace
    today = datetime.now(timezone.utc)

    def days_ago(n: int) -> datetime:
        return today - timedelta(days=n)

    workouts = [
        _build_continuous(2000, base_pace, "negative_split", "2K Test", days_ago(70), resting_hr, max_hr, 0.97, 32),
        _build_continuous(5000, base_pace * 1.03, "even", "5K Test", days_ago(63), resting_hr, max_hr, 0.88, 26),
        _build_continuous(6000, base_pace * 1.035, "positive_split", "6K Test", days_ago(56), resting_hr, max_hr, 0.86, 25),
        _build_continuous(10000, base_pace * 1.045, "positive_split", "10K Steady", days_ago(49), resting_hr, max_hr, 0.8, 22),
        _build_continuous(7500, base_pace * 1.06, "even", "30 Minute Steady State", days_ago(45), resting_hr, max_hr, 0.72, 20),
        _build_intervals(4, 1000, 180, base_pace * 0.99, "4 x 1K / 3min rest", days_ago(38), resting_hr, max_hr, 0.9, 29),
        _build_intervals(5, 500, 120, base_pace * 0.96, "5 x 500m / 2min rest", days_ago(31), resting_hr, max_hr, 0.94, 33),
        _build_intervals(3, 2000, 300, base_pace * 1.02, "3 x 2K / 5min rest", days_ago(24), resting_hr, max_hr, 0.89, 28),
        _build_continuous(6000, base_pace * 1.05, "fly_and_die", "Threshold Piece", days_ago(17), resting_hr, max_hr, 0.83, 24),
        _build_mixed_warmup_intervals_cooldown(base_pace, "Warmup + 4x500m + Cooldown", days_ago(10), resting_hr, max_hr),
        # A couple of recent pieces so trends have something current to show.
        _build_continuous(2000, base_pace * 0.995, "negative_split", "2K Test", days_ago(3), resting_hr, max_hr, 0.98, 32),
    ]
    return workouts


def _pace_str(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:04.1f}"


def get_or_create_demo_athlete(db, email: str, password: str) -> Athlete:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(email=email, hashed_password=hash_password(password))
        db.add(user)
        db.flush()
        athlete = Athlete(user_id=user.id, name=email.split("@")[0].title(), max_hr=185, resting_hr=50)
        db.add(athlete)
        db.commit()
        db.refresh(athlete)
        return athlete

    athlete = db.query(Athlete).filter(Athlete.user_id == user.id).order_by(Athlete.id.asc()).first()
    if athlete is None:
        athlete = Athlete(user_id=user.id, name=email.split("@")[0].title(), max_hr=185, resting_hr=50)
        db.add(athlete)
        db.commit()
        db.refresh(athlete)
    return athlete


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default="demo@example.com")
    parser.add_argument("--password", default="demo12345")
    parser.add_argument("--base-2k", default="6:50", help="Base 2K time as m:ss, used to scale all other pieces")
    args = parser.parse_args()

    minutes_str, seconds_str = args.base_2k.split(":")
    base_2k_seconds = int(minutes_str) * 60 + float(seconds_str)

    db = SessionLocal()
    try:
        athlete = get_or_create_demo_athlete(db, args.email, args.password)
        max_hr = athlete.max_hr or 185
        resting_hr = athlete.resting_hr or 50

        workouts = generate_workouts_for_athlete(base_2k_seconds, resting_hr, max_hr)
        for parsed in workouts:
            persist_parsed_workout(db, athlete.id, parsed, filename=None)

        print(f"Generated {len(workouts)} workouts for {args.email} (athlete_id={athlete.id}).")
        print(f"Base 2K pace: {_pace_str(base_2k_seconds / 4)}/500m ({_pace_str(base_2k_seconds)} for 2000m).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
