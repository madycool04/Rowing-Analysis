from datetime import datetime, timedelta, timezone

from app.models.segment import Segment, SegmentType
from app.models.workout import Workout, WorkoutCategory, WorkoutSource
from app.services.performance import build_progression_series, compute_personal_bests


def _continuous_workout(workout_id, distance, duration, date) -> Workout:
    w = Workout(
        athlete_id=1,
        source=WorkoutSource.MANUAL,
        category=WorkoutCategory.CONTINUOUS,
        title="Test",
        date=date,
        total_distance_m=distance,
        total_duration_s=duration,
        has_hr=False,
        has_splits=False,
        has_power=True,
        has_distance=True,
        has_stroke_rate=False,
    )
    w.id = workout_id
    segment = Segment(ordinal=0, type=SegmentType.WORK, start_time_s=0.0, duration_s=duration, distance_m=distance)
    segment.splits = []
    w.segments = [segment]
    return w


def _interval_workout(workout_id, rep_distance, rep_durations, date) -> Workout:
    w = Workout(
        athlete_id=1,
        source=WorkoutSource.MANUAL,
        category=WorkoutCategory.INTERVAL,
        title="Intervals",
        date=date,
        total_distance_m=rep_distance * len(rep_durations),
        total_duration_s=sum(rep_durations),
        has_hr=False,
        has_splits=True,
        has_power=True,
        has_distance=True,
        has_stroke_rate=False,
    )
    w.id = workout_id
    segments = []
    for i, d in enumerate(rep_durations):
        seg = Segment(ordinal=i, type=SegmentType.WORK, start_time_s=0.0, duration_s=d, distance_m=rep_distance)
        seg.splits = []
        segments.append(seg)
    w.segments = segments
    return w


class TestPersonalBests:
    def test_detects_2k_pb_from_continuous_workout(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        workouts = [_continuous_workout(1, 2000, 420.0, base)]
        pbs = compute_personal_bests(workouts)
        assert "2k" in pbs
        assert pbs["2k"]["current"]["duration_s"] == 420.0
        assert pbs["2k"]["previous"] is None
        assert pbs["2k"]["improvement_s"] is None

    def test_tracks_improvement_over_multiple_attempts(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        workouts = [
            _continuous_workout(1, 2000, 430.0, base),
            _continuous_workout(2, 2000, 420.0, base + timedelta(days=30)),
        ]
        pbs = compute_personal_bests(workouts)
        assert pbs["2k"]["current"]["duration_s"] == 420.0
        assert pbs["2k"]["previous"]["duration_s"] == 430.0
        assert pbs["2k"]["improvement_s"] == 10.0

    def test_slower_later_attempt_does_not_become_new_pb(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        workouts = [
            _continuous_workout(1, 2000, 410.0, base),
            _continuous_workout(2, 2000, 430.0, base + timedelta(days=10)),
        ]
        pbs = compute_personal_bests(workouts)
        assert pbs["2k"]["current"]["duration_s"] == 410.0
        assert pbs["2k"]["current"]["workout_id"] == 1

    def test_interval_rep_counts_toward_pb(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # A 4x1K session where one rep happens to be a fast 1K effort.
        workouts = [_interval_workout(1, 1000, [220.0, 218.0, 215.0, 222.0], base)]
        pbs = compute_personal_bests(workouts)
        assert "1k" in pbs
        assert pbs["1k"]["current"]["duration_s"] == 215.0

    def test_distance_tolerance_accepts_near_matches(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # 2005m is within 3% tolerance of 2000m.
        workouts = [_continuous_workout(1, 2005, 421.0, base)]
        pbs = compute_personal_bests(workouts)
        assert "2k" in pbs

    def test_distance_outside_tolerance_not_matched(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # 2200m is well outside 3% tolerance of 2000m.
        workouts = [_continuous_workout(1, 2200, 460.0, base)]
        pbs = compute_personal_bests(workouts)
        assert "2k" not in pbs

    def test_no_qualifying_efforts_yields_empty_dict(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        workouts = [_continuous_workout(1, 7500, 1800.0, base)]  # doesn't match any standard distance
        pbs = compute_personal_bests(workouts)
        assert pbs == {}


class TestProgressionSeries:
    def test_returns_chronological_series_for_distance(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        workouts = [
            _continuous_workout(2, 2000, 415.0, base + timedelta(days=10)),
            _continuous_workout(1, 2000, 425.0, base),
        ]
        series = build_progression_series(workouts, "2k")
        assert len(series) == 2
        assert series[0]["workout_id"] == 1  # earliest date first
        assert series[1]["workout_id"] == 2

    def test_unknown_label_returns_empty_list(self) -> None:
        workouts = [_continuous_workout(1, 2000, 420.0, datetime.now(timezone.utc))]
        assert build_progression_series(workouts, "not_a_distance") == []
