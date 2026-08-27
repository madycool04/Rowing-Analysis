from datetime import datetime, timedelta, timezone

import pytest

from app.models.athlete import Athlete
from app.models.workout import Workout, WorkoutCategory, WorkoutSource
from app.services.ml.baselines import pauls_law_2k_baseline, pauls_law_predict, previous_2k_baseline
from app.services.ml.features import build_feature_vector
from app.services.ml.train import walk_forward_validate


def _athlete(**overrides) -> Athlete:
    defaults = dict(user_id=1, name="Test Athlete", weight_kg=80.0, resting_hr=50, max_hr=185)
    defaults.update(overrides)
    return Athlete(**defaults)


def _workout(workout_id, distance, duration, date, avg_hr=150.0, avg_spm=28.0, has_splits=False) -> Workout:
    w = Workout(
        athlete_id=1,
        source=WorkoutSource.MANUAL,
        category=WorkoutCategory.CONTINUOUS,
        title="Test",
        date=date,
        total_distance_m=distance,
        total_duration_s=duration,
        has_hr=avg_hr is not None,
        has_splits=has_splits,
        has_power=True,
        has_distance=True,
        has_stroke_rate=avg_spm is not None,
        avg_hr=avg_hr,
        avg_stroke_rate=avg_spm,
    )
    w.id = workout_id
    # Deliberately NO segments: _collect_efforts() would otherwise count
    # both the whole-workout distance AND an identically-sized WORK
    # segment as two separate qualifying efforts, double-counting every
    # 2K in these tests. Segment-level effort detection (e.g. a rep
    # within a 4x1K) is already covered by test_performance.py.
    w.segments = []
    return w


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class TestPaulsLaw:
    def test_longer_reference_distance_predicts_faster_2k_pace(self) -> None:
        # A 5K time predicts a faster (lower) 2K pace than the 5K's own pace,
        # since pace should improve at shorter distances.
        time_5k = 1200.0  # 20:00 for 5000m -> 120s/500m
        predicted_2k = pauls_law_predict(time_5k, 5000.0, 2000.0)
        predicted_2k_pace = (predicted_2k / 2000.0) * 500.0
        assert predicted_2k_pace < 120.0

    def test_same_distance_returns_same_time(self) -> None:
        result = pauls_law_predict(420.0, 2000.0, 2000.0)
        assert result == pytest.approx(420.0)

    def test_rejects_non_positive_inputs(self) -> None:
        with pytest.raises(ValueError):
            pauls_law_predict(0, 2000.0, 2000.0)
        with pytest.raises(ValueError):
            pauls_law_predict(400.0, -100.0, 2000.0)


class TestPrevious2kBaseline:
    def test_unavailable_with_no_history(self) -> None:
        result = previous_2k_baseline([], before_date=BASE + timedelta(days=30))
        assert result["available"] is False

    def test_uses_most_recent_prior_2k(self) -> None:
        workouts = [
            _workout(1, 2000, 430.0, BASE),
            _workout(2, 2000, 420.0, BASE + timedelta(days=10)),
        ]
        result = previous_2k_baseline(workouts, before_date=BASE + timedelta(days=20))
        assert result["predicted_time_s"] == 420.0

    def test_respects_before_date_cutoff(self) -> None:
        workouts = [_workout(1, 2000, 420.0, BASE + timedelta(days=10))]
        # before_date is earlier than the only 2K - it must not be used.
        result = previous_2k_baseline(workouts, before_date=BASE)
        assert result["available"] is False


class TestPaulsLaw2kBaseline:
    def test_derives_from_5k_when_no_2k_available(self) -> None:
        workouts = [_workout(1, 5000, 1200.0, BASE)]
        result = pauls_law_2k_baseline(workouts, before_date=BASE + timedelta(days=1))
        assert result["available"] is True
        assert result["source"]["reference_distance_m"] == 5000.0

    def test_unavailable_without_any_reference_distance(self) -> None:
        workouts = [_workout(1, 7500, 1800.0, BASE)]  # doesn't match 5k/6k/10k
        result = pauls_law_2k_baseline(workouts, before_date=BASE + timedelta(days=1))
        assert result["available"] is False


class TestFeatureLeakagePrevention:
    def test_target_workout_itself_is_excluded(self) -> None:
        """The single most important test in this module."""
        athlete = _athlete()
        target_workout = _workout(1, 2000, 400.0, BASE)  # a very fast, distinctive time
        features = build_feature_vector(athlete, [target_workout], target_date=BASE)
        # With target_date == the workout's own date, _workouts_before (date < target_date)
        # must exclude it entirely - no feature should reflect its 400.0s time.
        assert features["recent_2k_pace"] is None
        assert features["avg_watts"] is None

    def test_future_workouts_never_used(self) -> None:
        athlete = _athlete()
        early = _workout(1, 2000, 430.0, BASE)
        future = _workout(2, 2000, 300.0, BASE + timedelta(days=30))  # implausibly fast, must not leak in
        features = build_feature_vector(athlete, [early, future], target_date=BASE + timedelta(days=10))
        # Only `early` (before day 10) should inform recent_2k_pace; must not reflect `future`.
        expected_pace = (430.0 / 2000.0) * 500.0
        assert features["recent_2k_pace"] == pytest.approx(expected_pace, abs=0.01)

    def test_uses_most_recent_prior_effort_not_earliest(self) -> None:
        athlete = _athlete()
        workouts = [
            _workout(1, 2000, 440.0, BASE),
            _workout(2, 2000, 410.0, BASE + timedelta(days=20)),
        ]
        features = build_feature_vector(athlete, workouts, target_date=BASE + timedelta(days=40))
        expected_pace = (410.0 / 2000.0) * 500.0
        assert features["recent_2k_pace"] == pytest.approx(expected_pace, abs=0.01)

    def test_athlete_weight_always_included(self) -> None:
        athlete = _athlete(weight_kg=75.5)
        features = build_feature_vector(athlete, [], target_date=BASE)
        assert features["athlete_weight_kg"] == 75.5

    def test_no_prior_workouts_yields_all_none_except_weight(self) -> None:
        athlete = _athlete()
        features = build_feature_vector(athlete, [], target_date=BASE)
        for key, value in features.items():
            if key == "athlete_weight_kg":
                continue
            assert value is None, f"{key} should be None with no prior data, got {value}"


class TestWalkForwardValidation:
    def test_unavailable_with_no_2k_history(self) -> None:
        athlete = _athlete()
        result = walk_forward_validate(athlete, [])
        assert result["available"] is False

    def test_insufficient_data_flag_below_five_tests(self) -> None:
        athlete = _athlete()
        workouts = [_workout(i, 2000, 420.0 - i, BASE + timedelta(days=i * 10)) for i in range(3)]
        result = walk_forward_validate(athlete, workouts)
        assert result["sufficient_data_for_ml"] is False
        assert result["n_historical_2k_tests"] == 3

    def test_sufficient_data_flag_at_five_or_more(self) -> None:
        athlete = _athlete()
        workouts = [_workout(i, 2000, 420.0 - i, BASE + timedelta(days=i * 10)) for i in range(6)]
        result = walk_forward_validate(athlete, workouts)
        assert result["sufficient_data_for_ml"] is True

    def test_first_fold_has_no_baseline_available(self) -> None:
        """The very first 2K in history has no prior 2K/5K/6K/10K to predict from."""
        athlete = _athlete()
        workouts = [_workout(1, 2000, 420.0, BASE)]
        result = walk_forward_validate(athlete, workouts)
        assert result["baselines"]["previous_2k"]["available"] is False

    def test_second_fold_can_use_previous_2k_baseline(self) -> None:
        athlete = _athlete()
        workouts = [
            _workout(1, 2000, 430.0, BASE),
            _workout(2, 2000, 420.0, BASE + timedelta(days=14)),
        ]
        result = walk_forward_validate(athlete, workouts)
        assert result["baselines"]["previous_2k"]["n_folds"] == 1
        assert result["baselines"]["previous_2k"]["mae_s"] == pytest.approx(10.0)

    def test_best_method_is_never_fabricated_when_nothing_available(self) -> None:
        athlete = _athlete()
        # A single 2K test: no baseline and no model can be evaluated (no prior data at all).
        workouts = [_workout(1, 2000, 420.0, BASE)]
        result = walk_forward_validate(athlete, workouts)
        assert result["best_method"] is None

    def test_walk_forward_is_chronological_not_random(self) -> None:
        athlete = _athlete()
        # Deliberately out-of-order input list - the function must sort by date itself.
        workouts = [
            _workout(2, 2000, 420.0, BASE + timedelta(days=20)),
            _workout(1, 2000, 430.0, BASE),
        ]
        result = walk_forward_validate(athlete, workouts)
        # Second (chronological) fold should be evaluated against the first as its baseline.
        assert result["baselines"]["previous_2k"]["n_folds"] == 1
        assert result["baselines"]["previous_2k"]["mae_s"] == pytest.approx(10.0)
