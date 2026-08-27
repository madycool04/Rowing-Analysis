from datetime import datetime, timedelta, timezone

from app.models.athlete import Athlete
from app.models.workout import Workout, WorkoutCategory, WorkoutSource
from app.services.ml.predictor import _build_explanation, _confidence_label, _conformal_margin, predict_2k

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _athlete(**overrides) -> Athlete:
    defaults = dict(user_id=1, name="Test Athlete", weight_kg=80.0, resting_hr=50, max_hr=185)
    defaults.update(overrides)
    return Athlete(**defaults)


def _workout(workout_id, distance, duration, date, avg_hr=150.0, avg_spm=28.0) -> Workout:
    w = Workout(
        athlete_id=1,
        source=WorkoutSource.MANUAL,
        category=WorkoutCategory.CONTINUOUS,
        title="Test",
        date=date,
        total_distance_m=distance,
        total_duration_s=duration,
        has_hr=avg_hr is not None,
        has_splits=False,
        has_power=True,
        has_distance=True,
        has_stroke_rate=avg_spm is not None,
        avg_hr=avg_hr,
        avg_stroke_rate=avg_spm,
    )
    w.id = workout_id
    w.segments = []
    return w


class TestConformalMargin:
    def test_none_below_minimum_samples(self) -> None:
        assert _conformal_margin([5.0, 3.0]) is None

    def test_margin_present_at_minimum_samples(self) -> None:
        assert _conformal_margin([5.0, 3.0, 8.0]) is not None

    def test_margin_reflects_worse_errors(self) -> None:
        tight = _conformal_margin([1.0, 2.0, 1.5, 2.0, 1.0])
        loose = _conformal_margin([10.0, 20.0, 15.0, 20.0, 10.0])
        assert loose > tight


class TestConfidenceLabel:
    def test_low_with_few_historical_tests(self) -> None:
        assert _confidence_label(n_historical_2k=2, calibration_samples=5) == "low"

    def test_low_with_few_calibration_samples_even_if_many_tests(self) -> None:
        assert _confidence_label(n_historical_2k=8, calibration_samples=1) == "low"

    def test_moderate_between_thresholds(self) -> None:
        assert _confidence_label(n_historical_2k=6, calibration_samples=5) == "moderate"

    def test_high_above_upper_threshold(self) -> None:
        assert _confidence_label(n_historical_2k=12, calibration_samples=10) == "high"


class TestExplanation:
    def test_empty_when_no_previous_prediction(self) -> None:
        factors = _build_explanation({"recent_5k_pace": 110.0}, previous_features=None)
        assert factors == []

    def test_lower_pace_is_positive_trend(self) -> None:
        factors = _build_explanation(
            {"recent_5k_pace": 108.0}, previous_features={"recent_5k_pace": 112.0}
        )
        assert factors[0]["trend"] == "positive"

    def test_higher_pace_is_negative_trend(self) -> None:
        factors = _build_explanation(
            {"recent_5k_pace": 115.0}, previous_features={"recent_5k_pace": 112.0}
        )
        assert factors[0]["trend"] == "negative"

    def test_higher_efficiency_factor_is_positive(self) -> None:
        factors = _build_explanation(
            {"efficiency_factor": 1.3}, previous_features={"efficiency_factor": 1.2}
        )
        assert factors[0]["trend"] == "positive"

    def test_missing_feature_on_either_side_is_skipped(self) -> None:
        factors = _build_explanation({"recent_5k_pace": 110.0}, previous_features={"recent_2k_pace": 100.0})
        assert factors == []

    def test_never_claims_causality(self) -> None:
        factors = _build_explanation(
            {"recent_5k_pace": 108.0}, previous_features={"recent_5k_pace": 112.0}
        )
        for f in factors:
            assert "because" not in f["trend"].lower()
            assert "causes" not in f["trend"].lower()


class TestPredict2k:
    def test_unavailable_with_no_data_at_all(self) -> None:
        athlete = _athlete()
        result = predict_2k(athlete, [], now=BASE)
        assert result["available"] is False

    def test_uses_previous_2k_when_only_one_historical_test(self) -> None:
        athlete = _athlete()
        workouts = [_workout(1, 2000, 420.0, BASE)]
        result = predict_2k(athlete, workouts, now=BASE + timedelta(days=10))
        assert result["available"] is True
        assert result["predicted_time_s"] == 420.0
        assert result["confidence"] == "low"

    def test_low_confidence_and_no_interval_with_sparse_history(self) -> None:
        athlete = _athlete()
        workouts = [
            _workout(1, 2000, 430.0, BASE),
            _workout(2, 2000, 420.0, BASE + timedelta(days=14)),
        ]
        result = predict_2k(athlete, workouts, now=BASE + timedelta(days=28))
        assert result["confidence"] == "low"
        assert result["lower_bound_s"] is None
        assert result["upper_bound_s"] is None

    def test_derives_from_pauls_law_when_no_2k_but_has_5k(self) -> None:
        athlete = _athlete()
        workouts = [_workout(1, 5000, 1200.0, BASE)]
        result = predict_2k(athlete, workouts, now=BASE + timedelta(days=5))
        assert result["available"] is True
        assert result["method_used"] == "pauls_law"

    def test_no_db_means_no_persistence_and_empty_factors(self) -> None:
        athlete = _athlete()
        workouts = [_workout(1, 2000, 420.0, BASE)]
        result = predict_2k(athlete, workouts, db=None, now=BASE + timedelta(days=10))
        assert result["contributing_factors"] == []
        assert result["change_vs_previous_s"] is None

    def test_note_never_claims_guarantee(self) -> None:
        athlete = _athlete()
        workouts = [_workout(1, 2000, 420.0, BASE)]
        result = predict_2k(athlete, workouts, now=BASE + timedelta(days=10))
        assert "not a guaranteed performance" in result["note"]
