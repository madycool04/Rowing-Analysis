import pytest

from app.models.segment import Segment, SegmentType
from app.models.split import Split
from app.models.workout import Workout, WorkoutCategory, WorkoutSource
from app.services.analytics import compute_workout_analytics
from app.utils.pace import watts_from_pace_per_500


def _split(ordinal, distance_m, elapsed_time_s, pace=None, watts=None, hr=None, spm=None, calories=None):
    return Split(
        ordinal=ordinal,
        distance_m=distance_m,
        elapsed_time_s=elapsed_time_s,
        pace_s_per_500=pace,
        watts=watts,
        heart_rate=hr,
        stroke_rate=spm,
        calories=calories,
    )


def _continuous_workout(splits: list[Split], has_hr=True, has_power=True, has_stroke_rate=True) -> Workout:
    total_distance = sum(s.distance_m for s in splits)
    total_duration = sum(s.elapsed_time_s for s in splits)
    segment = Segment(
        ordinal=0,
        type=SegmentType.WORK,
        start_time_s=0.0,
        duration_s=total_duration,
        distance_m=total_distance,
    )
    segment.splits = splits
    workout = Workout(
        athlete_id=1,
        source=WorkoutSource.MANUAL,
        category=WorkoutCategory.CONTINUOUS,
        title="Test",
        date=None,
        total_distance_m=total_distance,
        total_duration_s=total_duration,
        has_hr=has_hr,
        has_splits=True,
        has_power=has_power,
        has_distance=True,
        has_stroke_rate=has_stroke_rate,
    )
    workout.segments = [segment]
    return workout


class TestAveragePaceCorrectness:
    def test_avg_pace_is_total_time_over_total_distance_not_split_average(self) -> None:
        # Two splits with very different distances - naive pace-averaging
        # would give a materially different (wrong) answer than
        # total_time/total_distance.
        splits = [
            _split(0, 1000, 200.0, pace=100.0, watts=watts_from_pace_per_500(100.0)),
            _split(1, 500, 130.0, pace=130.0, watts=watts_from_pace_per_500(130.0)),
        ]
        workout = _continuous_workout(splits)
        result = compute_workout_analytics(workout)

        total_distance = 1500
        total_time = 330.0
        expected_pace = (total_time / total_distance) * 500.0  # = 110.0
        naive_average = (100.0 + 130.0) / 2  # = 115.0 (WRONG, must not equal this)

        actual = result["metrics"]["basic"]["avg_pace_s_per_500"]
        assert actual == pytest.approx(expected_pace, abs=0.01)
        assert actual != pytest.approx(naive_average, abs=0.01)


class TestPacingEvenness:
    def test_low_cv_for_even_pacing(self) -> None:
        splits = [_split(i, 500, 100.0, pace=100.0, watts=watts_from_pace_per_500(100.0)) for i in range(4)]
        workout = _continuous_workout(splits)
        result = compute_workout_analytics(workout)
        cv = result["metrics"]["pacing"]["pacing_cv_pct"]
        assert cv == pytest.approx(0.0, abs=0.01)

    def test_higher_cv_for_uneven_pacing(self) -> None:
        paces = [90.0, 100.0, 110.0, 120.0]
        splits = [_split(i, 500, p, pace=p, watts=watts_from_pace_per_500(p)) for i, p in enumerate(paces)]
        workout = _continuous_workout(splits)
        result = compute_workout_analytics(workout)
        cv = result["metrics"]["pacing"]["pacing_cv_pct"]
        assert cv > 5.0

    def test_pacing_unavailable_with_insufficient_splits(self) -> None:
        splits = [_split(0, 500, 100.0, pace=100.0, watts=watts_from_pace_per_500(100.0))]
        workout = _continuous_workout(splits)
        workout.has_splits = True
        result = compute_workout_analytics(workout)
        assert result["metrics"]["pacing"]["pacing_cv_pct"] is None
        assert result["data_quality"]["pacing_evenness_available"] is False


class TestPaceFade:
    def test_positive_fade_when_final_quarter_slower(self) -> None:
        paces = [95.0, 96.0, 100.0, 108.0]  # slowing down toward the end
        splits = [_split(i, 500, p, pace=p, watts=watts_from_pace_per_500(p)) for i, p in enumerate(paces)]
        workout = _continuous_workout(splits)
        result = compute_workout_analytics(workout)
        fade = result["metrics"]["pacing"]["pace_fade_pct"]
        assert fade > 0

    def test_negative_fade_when_final_quarter_faster(self) -> None:
        paces = [108.0, 100.0, 96.0, 92.0]  # negative split
        splits = [_split(i, 500, p, pace=p, watts=watts_from_pace_per_500(p)) for i, p in enumerate(paces)]
        workout = _continuous_workout(splits)
        result = compute_workout_analytics(workout)
        fade = result["metrics"]["pacing"]["pace_fade_pct"]
        assert fade < 0

    def test_fade_unavailable_with_fewer_than_four_splits(self) -> None:
        paces = [100.0, 102.0]
        splits = [_split(i, 500, p, pace=p, watts=watts_from_pace_per_500(p)) for i, p in enumerate(paces)]
        workout = _continuous_workout(splits)
        result = compute_workout_analytics(workout)
        assert result["metrics"]["pacing"]["pace_fade_pct"] is None
        assert result["data_quality"]["pace_fade_available"] is False


class TestHalfComparison:
    def test_negative_split_detected(self) -> None:
        paces = [110.0, 108.0, 100.0, 98.0]
        splits = [_split(i, 500, p, pace=p, watts=watts_from_pace_per_500(p)) for i, p in enumerate(paces)]
        workout = _continuous_workout(splits)
        result = compute_workout_analytics(workout)
        first_half = result["metrics"]["pacing"]["first_half"]
        second_half = result["metrics"]["pacing"]["second_half"]
        assert second_half["avg_pace_s_per_500"] < first_half["avg_pace_s_per_500"]


class TestDataQualityGating:
    def test_no_splits_workout_only_has_basic_metrics(self) -> None:
        workout = Workout(
            athlete_id=1,
            source=WorkoutSource.CONCEPT2_CSV_SUMMARY,
            category=WorkoutCategory.CONTINUOUS,
            title="Summary only",
            date=None,
            total_distance_m=2000.0,
            total_duration_s=425.0,
            has_hr=False,
            has_splits=False,
            has_power=True,
            has_distance=True,
            has_stroke_rate=False,
        )
        segment = Segment(ordinal=0, type=SegmentType.WORK, start_time_s=0.0, duration_s=425.0, distance_m=2000.0)
        segment.splits = []
        workout.segments = [segment]

        result = compute_workout_analytics(workout)
        assert result["metrics"]["basic"]["total_distance_m"] == 2000.0
        assert result["metrics"]["pacing"]["pacing_cv_pct"] is None
        assert result["data_quality"]["has_splits"] is False
        assert result["data_quality"]["pacing_evenness_available"] is False

    def test_missing_hr_yields_none_avg_hr_not_zero(self) -> None:
        splits = [_split(i, 500, 100.0, pace=100.0, watts=watts_from_pace_per_500(100.0), hr=None) for i in range(4)]
        workout = _continuous_workout(splits, has_hr=False)
        result = compute_workout_analytics(workout)
        assert result["metrics"]["basic"]["avg_hr"] is None


class TestIntervalAnalysis:
    def _interval_workout(self, interval_watts: list[float]) -> Workout:
        segments = []
        for i, w in enumerate(interval_watts):
            work = Segment(ordinal=len(segments), type=SegmentType.WORK, start_time_s=0.0, duration_s=200.0, distance_m=1000.0)
            work.splits = [_split(0, 1000.0, 200.0, watts=w)]
            segments.append(work)
            if i < len(interval_watts) - 1:
                rest = Segment(ordinal=len(segments), type=SegmentType.REST, start_time_s=0.0, duration_s=90.0, distance_m=0.0)
                rest.splits = []
                segments.append(rest)

        total_distance = 1000.0 * len(interval_watts)
        total_duration = 200.0 * len(interval_watts) + 90.0 * (len(interval_watts) - 1)
        workout = Workout(
            athlete_id=1,
            source=WorkoutSource.MANUAL,
            category=WorkoutCategory.INTERVAL,
            title="Intervals",
            date=None,
            total_distance_m=total_distance,
            total_duration_s=total_duration,
            has_hr=False,
            has_splits=True,
            has_power=True,
            has_distance=True,
            has_stroke_rate=False,
        )
        workout.segments = segments
        return workout

    def test_declining_watts_gives_negative_slope(self) -> None:
        workout = self._interval_workout([300, 295, 290, 285])
        result = compute_workout_analytics(workout)
        decay = result["metrics"]["intervals"]["decay"]
        assert decay["slope_watts_per_interval"] < 0
        assert "fade" in decay["interpretation"].lower()

    def test_stable_watts_gives_near_zero_slope(self) -> None:
        workout = self._interval_workout([300, 300, 300, 300])
        result = compute_workout_analytics(workout)
        decay = result["metrics"]["intervals"]["decay"]
        assert decay["slope_watts_per_interval"] == pytest.approx(0.0, abs=0.01)

    def test_noisy_warning_present_for_few_intervals(self) -> None:
        workout = self._interval_workout([300, 295, 290, 285])
        result = compute_workout_analytics(workout)
        assert "noisy_estimate_warning" in result["metrics"]["intervals"]["decay"]

    def test_work_rest_ratio_computed(self) -> None:
        workout = self._interval_workout([300, 295, 290, 285])
        result = compute_workout_analytics(workout)
        ratio = result["metrics"]["intervals"]["work_rest_ratio"]
        # 4 x 200s work / 3 x 90s rest = 800/270
        assert ratio == pytest.approx(800 / 270, abs=0.01)

    def test_interval_analysis_unavailable_for_single_interval(self) -> None:
        workout = self._interval_workout([300])
        result = compute_workout_analytics(workout)
        assert result["metrics"]["intervals"] is None
        assert result["data_quality"]["interval_analysis_available"] is False

    def test_best_and_worst_interval_identified(self) -> None:
        workout = self._interval_workout([280, 310, 290, 275])
        result = compute_workout_analytics(workout)
        intervals = result["metrics"]["intervals"]
        assert intervals["best_interval_index"] == 1
        assert intervals["worst_interval_index"] == 3
