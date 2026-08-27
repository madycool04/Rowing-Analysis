from datetime import datetime, timedelta, timezone

import pytest

from app.models.athlete import Athlete, Sex
from app.models.workout import Workout, WorkoutCategory, WorkoutSource
from app.services.training_load import banister_trimp, build_daily_load_series, compute_workout_training_load


def _athlete(resting_hr=50, max_hr=185, sex=None, best_2k_seconds=None) -> Athlete:
    return Athlete(
        user_id=1,
        name="Test Athlete",
        resting_hr=resting_hr,
        max_hr=max_hr,
        sex=sex,
        best_2k_seconds=best_2k_seconds,
    )


def _workout(distance=6000.0, duration=1500.0) -> Workout:
    return Workout(
        athlete_id=1,
        source=WorkoutSource.MANUAL,
        category=WorkoutCategory.CONTINUOUS,
        title="Steady",
        date=datetime.now(timezone.utc),
        total_distance_m=distance,
        total_duration_s=duration,
        has_hr=True,
        has_splits=False,
        has_power=True,
        has_distance=True,
        has_stroke_rate=False,
    )


class TestBanisterTrimp:
    def test_higher_hr_gives_higher_trimp(self) -> None:
        low = banister_trimp(duration_min=30, avg_hr=130, resting_hr=50, max_hr=185, sex=None)
        high = banister_trimp(duration_min=30, avg_hr=170, resting_hr=50, max_hr=185, sex=None)
        assert high > low

    def test_longer_duration_gives_higher_trimp(self) -> None:
        short = banister_trimp(duration_min=20, avg_hr=150, resting_hr=50, max_hr=185, sex=None)
        long_ = banister_trimp(duration_min=60, avg_hr=150, resting_hr=50, max_hr=185, sex=None)
        assert long_ > short

    def test_returns_none_for_invalid_hr_range(self) -> None:
        result = banister_trimp(duration_min=30, avg_hr=150, resting_hr=185, max_hr=185, sex=None)
        assert result is None

    def test_female_and_male_coefficients_differ(self) -> None:
        male = banister_trimp(duration_min=30, avg_hr=160, resting_hr=50, max_hr=185, sex=None)
        female = banister_trimp(duration_min=30, avg_hr=160, resting_hr=50, max_hr=185, sex=Sex.FEMALE)
        assert male != female


class TestComputeWorkoutTrainingLoad:
    def test_uses_trimp_when_hr_and_profile_available(self) -> None:
        athlete = _athlete()
        workout = _workout()
        result = compute_workout_training_load(workout, athlete, avg_hr=150.0, reference_2k_watts=300.0)
        assert result["method"] == "trimp"
        assert result["value"] is not None

    def test_falls_back_without_hr_profile(self) -> None:
        athlete = _athlete(resting_hr=None, max_hr=None)
        workout = _workout()
        result = compute_workout_training_load(workout, athlete, avg_hr=None, reference_2k_watts=250.0)
        assert result["method"] == "fallback"
        assert result["value"] is not None
        assert "analytical estimate" in result["note"].lower() or "estimate" in result["note"].lower()

    def test_unavailable_without_hr_or_reference(self) -> None:
        athlete = _athlete(resting_hr=None, max_hr=None)
        workout = _workout()
        result = compute_workout_training_load(workout, athlete, avg_hr=None, reference_2k_watts=None)
        assert result["method"] == "unavailable"
        assert result["value"] is None

    def test_fallback_scales_with_intensity(self) -> None:
        athlete = _athlete(resting_hr=None, max_hr=None)
        easy = _workout(distance=6000, duration=1800)  # slower pace
        hard = _workout(distance=6000, duration=1400)  # faster pace, same distance
        reference = 300.0
        easy_load = compute_workout_training_load(easy, athlete, avg_hr=None, reference_2k_watts=reference)
        hard_load = compute_workout_training_load(hard, athlete, avg_hr=None, reference_2k_watts=reference)
        # Hard workout is both shorter AND at higher intensity than easy;
        # intensity factor should still be meaningfully higher.
        hard_intensity = hard_load["value"] / (hard.total_duration_s / 60.0)
        easy_intensity = easy_load["value"] / (easy.total_duration_s / 60.0)
        assert hard_intensity > easy_intensity


class TestDailyLoadSeries:
    def test_empty_input_returns_empty_series(self) -> None:
        assert build_daily_load_series([]) == []

    def test_single_day_load_appears_correctly(self) -> None:
        d = datetime(2026, 8, 1, tzinfo=timezone.utc)
        series = build_daily_load_series([(d, 100.0)])
        assert len(series) == 1
        assert series[0]["daily_load"] == 100.0
        assert series[0]["rolling_7_day"] == 100.0
        assert series[0]["rolling_28_day"] == 100.0

    def test_rolling_windows_accumulate_correctly(self) -> None:
        base = datetime(2026, 8, 1, tzinfo=timezone.utc)
        loads = [(base + timedelta(days=i), 50.0) for i in range(10)]
        series = build_daily_load_series(loads)
        last = series[-1]
        # Day 10 (index 9): last 7 days each have 50 load -> 350
        assert last["rolling_7_day"] == pytest.approx(350.0)
        # All 10 days so far have loaded -> 500 (< 28 day window cap)
        assert last["rolling_28_day"] == pytest.approx(500.0)

    def test_none_load_on_a_day_with_another_valid_workout_does_not_corrupt_total(self) -> None:
        d = datetime(2026, 8, 1, tzinfo=timezone.utc)
        # Two workouts on the same day - one with an unavailable load, one with a real value.
        series = build_daily_load_series([(d, None), (d, 100.0)])
        assert len(series) == 1
        assert series[0]["daily_load"] == 100.0

    def test_gap_days_with_no_workouts_show_as_zero(self) -> None:
        d = datetime(2026, 8, 1, tzinfo=timezone.utc)
        # No workout at all on day 2 (d+1) - the series must still include
        # it as a zero-load day so rolling windows stay contiguous.
        series = build_daily_load_series([(d, 100.0), (d + timedelta(days=2), 50.0)])
        assert len(series) == 3
        assert series[1]["daily_load"] == 0.0

    def test_acwr_present_when_chronic_load_nonzero(self) -> None:
        base = datetime(2026, 8, 1, tzinfo=timezone.utc)
        loads = [(base + timedelta(days=i), 50.0) for i in range(30)]
        series = build_daily_load_series(loads)
        last = series[-1]
        assert last["acwr"] is not None
        assert last["acwr"] == pytest.approx(1.0, abs=0.05)  # steady load -> ACWR near 1.0
