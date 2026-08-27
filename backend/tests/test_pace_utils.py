import pytest

from app.utils.pace import (
    average_pace_per_500,
    average_watts_from_totals,
    format_duration,
    format_pace,
    parse_pace_to_seconds,
    pace_per_500_from_watts,
    watts_from_pace_per_500,
)


class TestWattsPaceConversion:
    def test_known_concept2_reference_point(self) -> None:
        # 2:00/500m is a commonly-cited Concept2 reference: ~124.7W
        watts = watts_from_pace_per_500(120.0)
        assert watts == pytest.approx(2.80 / (120.0 / 500.0) ** 3, abs=0.01)

    def test_faster_pace_yields_higher_watts(self) -> None:
        assert watts_from_pace_per_500(100.0) > watts_from_pace_per_500(120.0)

    def test_round_trip_pace_to_watts_to_pace(self) -> None:
        original_pace = 105.3
        watts = watts_from_pace_per_500(original_pace)
        recovered_pace = pace_per_500_from_watts(watts)
        assert recovered_pace == pytest.approx(original_pace, abs=0.01)

    def test_round_trip_watts_to_pace_to_watts(self) -> None:
        original_watts = 250.0
        pace = pace_per_500_from_watts(original_watts)
        recovered_watts = watts_from_pace_per_500(pace)
        assert recovered_watts == pytest.approx(original_watts, abs=0.01)

    def test_rejects_non_positive_pace(self) -> None:
        with pytest.raises(ValueError):
            watts_from_pace_per_500(0)
        with pytest.raises(ValueError):
            watts_from_pace_per_500(-10)

    def test_rejects_non_positive_watts(self) -> None:
        with pytest.raises(ValueError):
            pace_per_500_from_watts(0)
        with pytest.raises(ValueError):
            pace_per_500_from_watts(-10)


class TestAveragePaceCorrectness:
    def test_matches_manual_calculation(self) -> None:
        # 2000m in 420s -> (420/2000)*500 = 105.0 s/500m
        assert average_pace_per_500(2000.0, 420.0) == pytest.approx(105.0)

    def test_does_not_equal_naive_average_of_different_split_paces(self) -> None:
        # Two unequal-distance splits: naive averaging of their individual
        # paces gives a different (wrong) number than total_time/total_distance.
        # Split A: 1000m in 200s (pace 100s/500m). Split B: 500m in 110s (pace 110s/500m).
        total_distance, total_time = 1500.0, 310.0
        correct = average_pace_per_500(total_distance, total_time)
        naive_average_of_paces = (100.0 + 110.0) / 2
        assert correct != pytest.approx(naive_average_of_paces, abs=0.01)
        assert correct == pytest.approx((310.0 / 1500.0) * 500.0)

    def test_rejects_non_positive_inputs(self) -> None:
        with pytest.raises(ValueError):
            average_pace_per_500(0, 100.0)
        with pytest.raises(ValueError):
            average_pace_per_500(100.0, 0)

    def test_average_watts_from_totals_is_consistent_with_average_pace(self) -> None:
        watts = average_watts_from_totals(2000.0, 420.0)
        expected = watts_from_pace_per_500(average_pace_per_500(2000.0, 420.0))
        assert watts == pytest.approx(expected)


class TestFormatting:
    def test_format_pace_standard_case(self) -> None:
        assert format_pace(112.3) == "1:52.3"

    def test_format_pace_under_a_minute(self) -> None:
        assert format_pace(45.6) == "0:45.6"

    def test_format_pace_none_passthrough(self) -> None:
        assert format_pace(None) is None

    def test_format_duration_under_an_hour(self) -> None:
        assert format_duration(125.4) == "2:05.4"

    def test_format_duration_over_an_hour(self) -> None:
        assert format_duration(3725.0) == "1:02:05.0"


class TestParsePace:
    def test_parses_mmss_format(self) -> None:
        assert parse_pace_to_seconds("1:52.3") == pytest.approx(112.3)

    def test_parses_plain_seconds(self) -> None:
        assert parse_pace_to_seconds("105.0") == pytest.approx(105.0)

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError):
            parse_pace_to_seconds("")

    def test_rejects_garbage_string(self) -> None:
        with pytest.raises(ValueError):
            parse_pace_to_seconds("not-a-pace")
