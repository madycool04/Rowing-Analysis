import pytest

from app.models.athlete import DEFAULT_HR_ZONE_CONFIG, Athlete
from app.models.split import Split
from app.models.workout import Workout, WorkoutCategory, WorkoutSource
from app.services.analytics import WorkSplitRef
from app.services.hr_zones import (
    compute_cardiac_decoupling,
    compute_efficiency_factor,
    compute_hr_drift,
    compute_hr_zone_breakdown,
)
from app.utils.pace import watts_from_pace_per_500


def _ref(hr=None, elapsed=100.0, distance=500.0, watts=None, pace=None, ordinal=0, segment_ordinal=0):
    split = Split(
        ordinal=ordinal,
        distance_m=distance,
        elapsed_time_s=elapsed,
        heart_rate=hr,
        watts=watts,
        pace_s_per_500=pace,
    )
    return WorkSplitRef(split=split, segment_ordinal=segment_ordinal)


def _athlete(max_hr=185, hr_zone_config=None) -> Athlete:
    return Athlete(
        user_id=1,
        name="Test Athlete",
        max_hr=max_hr,
        hr_zone_config=hr_zone_config or DEFAULT_HR_ZONE_CONFIG,
    )


class TestHrZoneBreakdown:
    def test_unavailable_without_max_hr(self) -> None:
        athlete = _athlete(max_hr=None)
        refs = [_ref(hr=150, elapsed=100)]
        metrics, notes = compute_hr_zone_breakdown(refs, athlete)
        assert metrics is None
        assert notes["hr_zones_available"] is False

    def test_unavailable_without_any_hr_data(self) -> None:
        athlete = _athlete()
        refs = [_ref(hr=None, elapsed=100)]
        metrics, notes = compute_hr_zone_breakdown(refs, athlete)
        assert metrics is None
        assert notes["hr_zones_available"] is False

    def test_zone_percentages_sum_to_100(self) -> None:
        athlete = _athlete(max_hr=200)
        # Zone 1: 100-120, Zone 2: 120-140, Zone 3: 140-160, Zone 4: 160-180, Zone 5: 180-220
        refs = [
            _ref(hr=110, elapsed=60),  # zone 1
            _ref(hr=150, elapsed=60),  # zone 3
            _ref(hr=190, elapsed=60),  # zone 5
        ]
        metrics, notes = compute_hr_zone_breakdown(refs, athlete)
        assert notes["hr_zones_available"] is True
        total_pct = sum(z["pct"] for z in metrics["zones"])
        assert total_pct == pytest.approx(100.0, abs=0.1)

    def test_correct_zone_assignment(self) -> None:
        athlete = _athlete(max_hr=200)
        refs = [_ref(hr=110, elapsed=100)]  # 55% of 200 -> zone 1 (50-60%)
        metrics, _ = compute_hr_zone_breakdown(refs, athlete)
        zone_1 = next(z for z in metrics["zones"] if z["zone"] == 1)
        assert zone_1["time_s"] == pytest.approx(100.0)
        assert zone_1["pct"] == pytest.approx(100.0)

    def test_avg_hr_is_time_weighted(self) -> None:
        athlete = _athlete()
        refs = [_ref(hr=150, elapsed=100), _ref(hr=170, elapsed=300)]
        metrics, _ = compute_hr_zone_breakdown(refs, athlete)
        expected = (150 * 100 + 170 * 300) / 400
        assert metrics["avg_hr"] == pytest.approx(expected, abs=0.1)


class TestEfficiencyFactor:
    def test_unavailable_without_hr(self) -> None:
        metrics, notes = compute_efficiency_factor({"avg_watts": 250.0, "avg_hr": None})
        assert metrics is None
        assert notes["efficiency_factor_available"] is False

    def test_unavailable_without_watts(self) -> None:
        metrics, notes = compute_efficiency_factor({"avg_watts": None, "avg_hr": 150.0})
        assert metrics is None
        assert notes["efficiency_factor_available"] is False

    def test_computes_ratio_correctly(self) -> None:
        metrics, notes = compute_efficiency_factor({"avg_watts": 200.0, "avg_hr": 160.0})
        assert notes["efficiency_factor_available"] is True
        assert metrics["efficiency_factor"] == pytest.approx(1.25, abs=0.001)
        assert "descriptive training metric" in metrics["note"]


class TestCardiacDecoupling:
    def _workout(self, duration_s, hr_coverage_pct, has_power=True) -> Workout:
        return Workout(
            athlete_id=1,
            source=WorkoutSource.MANUAL,
            category=WorkoutCategory.CONTINUOUS,
            title="Steady state",
            date=None,
            total_distance_m=10000.0,
            total_duration_s=duration_s,
            has_hr=True,
            has_splits=True,
            has_power=has_power,
            has_distance=True,
            has_stroke_rate=False,
            hr_coverage_pct=hr_coverage_pct,
        )

    def test_unavailable_under_20_minutes(self) -> None:
        workout = self._workout(duration_s=900, hr_coverage_pct=100.0)
        refs = [_ref(hr=150, watts=200, elapsed=450), _ref(hr=155, watts=195, elapsed=450)]
        metrics, notes = compute_cardiac_decoupling(workout, refs)
        assert metrics is None
        assert notes["cardiac_decoupling_available"] is False

    def test_unavailable_with_low_hr_coverage(self) -> None:
        workout = self._workout(duration_s=1500, hr_coverage_pct=60.0)
        refs = [_ref(hr=150, watts=200, elapsed=750), _ref(hr=155, watts=195, elapsed=750)]
        metrics, notes = compute_cardiac_decoupling(workout, refs)
        assert metrics is None
        assert notes["cardiac_decoupling_available"] is False

    def test_positive_decoupling_when_hr_rises_relative_to_power(self) -> None:
        workout = self._workout(duration_s=1800, hr_coverage_pct=100.0)
        # First half: strong watts at moderate HR. Second half: same watts, higher HR (worse EF).
        pace = 110.0
        watts = watts_from_pace_per_500(pace)
        first_half = [_ref(hr=150, elapsed=450, distance=1000, pace=pace, watts=watts) for _ in range(2)]
        second_half = [_ref(hr=175, elapsed=450, distance=1000, pace=pace, watts=watts) for _ in range(2)]
        metrics, notes = compute_cardiac_decoupling(workout, first_half + second_half)
        assert notes["cardiac_decoupling_available"] is True
        assert metrics["decoupling_pct"] > 0

    def test_note_frames_5pct_as_heuristic_not_fact(self) -> None:
        workout = self._workout(duration_s=1800, hr_coverage_pct=100.0)
        pace = 110.0
        watts = watts_from_pace_per_500(pace)
        refs = [_ref(hr=150, elapsed=450, distance=1000, pace=pace, watts=watts) for _ in range(4)]
        metrics, _ = compute_cardiac_decoupling(workout, refs)
        assert "heuristic" in metrics["note"].lower()


class TestHrDrift:
    def test_unavailable_when_pacing_cv_none(self) -> None:
        refs = [_ref(hr=150, elapsed=100) for _ in range(4)]
        metrics, notes = compute_hr_drift(refs, pacing_cv_pct=None)
        assert metrics is None
        assert notes["hr_drift_available"] is False

    def test_unavailable_when_pace_unstable(self) -> None:
        refs = [_ref(hr=150, elapsed=100) for _ in range(4)]
        metrics, notes = compute_hr_drift(refs, pacing_cv_pct=8.0)
        assert metrics is None
        assert "not sufficiently stable" in notes["hr_drift_unavailable_reason"]

    def test_unavailable_with_too_few_splits(self) -> None:
        refs = [_ref(hr=150, elapsed=100), _ref(hr=155, elapsed=100)]
        metrics, notes = compute_hr_drift(refs, pacing_cv_pct=1.0)
        assert metrics is None
        assert notes["hr_drift_available"] is False

    def test_positive_drift_when_hr_rises_at_stable_pace(self) -> None:
        refs = [
            _ref(hr=150, elapsed=100),
            _ref(hr=152, elapsed=100),
            _ref(hr=165, elapsed=100),
            _ref(hr=168, elapsed=100),
        ]
        metrics, notes = compute_hr_drift(refs, pacing_cv_pct=1.5)
        assert notes["hr_drift_available"] is True
        assert metrics["drift_pct"] > 0
