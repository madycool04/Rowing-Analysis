"""
Core per-workout analytics (spec sections 11-12).

Every computation here checks data availability first and returns an
explicit "unavailable" reason rather than a misleading number - this is
the primary way the {"metrics", "data_quality", "insights"} contract
(spec section 10) stays honest.

Nothing in this module averages split paces directly; all pace
aggregates route through app.utils.pace.average_pace_per_500 (total
time / total distance), per spec section 8.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.models.segment import Segment, SegmentType
from app.models.split import Split
from app.models.workout import Workout
from app.utils.pace import average_pace_per_500, format_pace, watts_from_pace_per_500

MIN_SPLITS_FOR_PACING = 2
MIN_SPLITS_FOR_QUARTILE_FADE = 4
MIN_INTERVALS_FOR_DECAY = 2
NOISY_INTERVAL_COUNT_THRESHOLD = 5


@dataclass
class WorkSplitRef:
    """A split plus which work segment (by ordinal) it belongs to, in chronological order."""

    split: Split
    segment_ordinal: int


def _flatten_work_splits(workout: Workout) -> list[WorkSplitRef]:
    refs: list[WorkSplitRef] = []
    for segment in sorted(workout.segments, key=lambda s: s.ordinal):
        if segment.type != SegmentType.WORK:
            continue
        for split in sorted(segment.splits, key=lambda s: s.ordinal):
            refs.append(WorkSplitRef(split=split, segment_ordinal=segment.ordinal))
    return refs


def _work_segments(workout: Workout) -> list[Segment]:
    return sorted(
        (s for s in workout.segments if s.type == SegmentType.WORK),
        key=lambda s: s.ordinal,
    )


def _rest_segments(workout: Workout) -> list[Segment]:
    return sorted(
        (s for s in workout.segments if s.type == SegmentType.REST),
        key=lambda s: s.ordinal,
    )


def _weighted_average(values_and_weights: list[tuple[float, float]]) -> float | None:
    total_weight = sum(w for _, w in values_and_weights)
    if total_weight <= 0:
        return None
    return sum(v * w for v, w in values_and_weights) / total_weight


def _coefficient_of_variation_pct(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = statistics.mean(values)
    if mean == 0:
        return None
    stdev = statistics.stdev(values)  # sample stdev
    return (stdev / mean) * 100.0


def _basic_metrics(workout: Workout, work_splits: list[WorkSplitRef]) -> dict:
    avg_pace = average_pace_per_500(workout.total_distance_m, workout.total_duration_s)
    avg_watts = watts_from_pace_per_500(avg_pace)

    hr_weighted = [
        (ref.split.heart_rate, ref.split.elapsed_time_s)
        for ref in work_splits
        if ref.split.heart_rate is not None
    ]
    spm_weighted = [
        (ref.split.stroke_rate, ref.split.elapsed_time_s)
        for ref in work_splits
        if ref.split.stroke_rate is not None
    ]
    calories_values = [ref.split.calories for ref in work_splits if ref.split.calories is not None]
    watts_values = [ref.split.watts for ref in work_splits if ref.split.watts is not None]
    pace_values = [ref.split.pace_s_per_500 for ref in work_splits if ref.split.pace_s_per_500 is not None]
    hr_values = [ref.split.heart_rate for ref in work_splits if ref.split.heart_rate is not None]

    return {
        "total_distance_m": workout.total_distance_m,
        "total_duration_s": workout.total_duration_s,
        "avg_pace_s_per_500": round(avg_pace, 2),
        "avg_pace_display": format_pace(avg_pace),
        "avg_watts": round(avg_watts, 1),
        "avg_hr": round(_weighted_average(hr_weighted), 1) if hr_weighted else None,
        "max_hr": max(hr_values) if hr_values else None,
        "avg_stroke_rate": round(_weighted_average(spm_weighted), 1) if spm_weighted else None,
        "calories": round(sum(calories_values), 1) if calories_values else None,
        "max_watts": round(max(watts_values), 1) if watts_values else None,
        "min_pace_s_per_500": round(min(pace_values), 2) if pace_values else None,
        "max_pace_s_per_500": round(max(pace_values), 2) if pace_values else None,
    }


def _pacing_metrics(work_splits: list[WorkSplitRef]) -> tuple[dict, dict]:
    """Returns (metrics, data_quality_notes)."""
    notes: dict = {}
    metrics: dict = {}

    watts_values = [ref.split.watts for ref in work_splits if ref.split.watts is not None]
    if len(watts_values) >= MIN_SPLITS_FOR_PACING:
        metrics["pacing_cv_pct"] = round(_coefficient_of_variation_pct(watts_values) or 0.0, 2)
        notes["pacing_evenness_available"] = True
    else:
        metrics["pacing_cv_pct"] = None
        notes["pacing_evenness_available"] = False
        notes["pacing_evenness_unavailable_reason"] = (
            "At least 2 splits with power data are required to assess pacing evenness."
        )

    pace_values = [ref.split.pace_s_per_500 for ref in work_splits if ref.split.pace_s_per_500 is not None]
    if len(pace_values) >= MIN_SPLITS_FOR_QUARTILE_FADE:
        mean_pace = statistics.mean(pace_values)
        quartile_size = max(len(pace_values) // 4, 1)
        final_quartile = pace_values[-quartile_size:]
        final_quartile_mean = statistics.mean(final_quartile)
        fade_pct = ((final_quartile_mean - mean_pace) / mean_pace) * 100.0
        metrics["pace_fade_pct"] = round(fade_pct, 2)
        notes["pace_fade_available"] = True
    else:
        metrics["pace_fade_pct"] = None
        notes["pace_fade_available"] = False
        notes["pace_fade_unavailable_reason"] = (
            "At least 4 splits are required to compute a quartile-based pace fade."
        )

    if len(work_splits) >= MIN_SPLITS_FOR_PACING:
        midpoint = len(work_splits) // 2
        first_half = work_splits[:midpoint] if midpoint > 0 else work_splits[:1]
        second_half = work_splits[midpoint:] if midpoint > 0 else work_splits[1:]

        def _half_summary(half: list[WorkSplitRef]) -> dict | None:
            distance = sum(r.split.distance_m for r in half)
            duration = sum(r.split.elapsed_time_s for r in half)
            if distance <= 0 or duration <= 0:
                return None
            pace = average_pace_per_500(distance, duration)
            return {
                "avg_pace_s_per_500": round(pace, 2),
                "avg_pace_display": format_pace(pace),
                "avg_watts": round(watts_from_pace_per_500(pace), 1),
            }

        metrics["first_half"] = _half_summary(first_half)
        metrics["second_half"] = _half_summary(second_half)
        notes["half_split_comparison_available"] = True
    else:
        metrics["first_half"] = None
        metrics["second_half"] = None
        notes["half_split_comparison_available"] = False
        notes["half_split_comparison_unavailable_reason"] = (
            "At least 2 splits are required to compare first vs second half."
        )

    if pace_values:
        fastest_idx = min(range(len(work_splits)), key=lambda i: work_splits[i].split.pace_s_per_500 or float("inf"))
        slowest_idx = max(range(len(work_splits)), key=lambda i: work_splits[i].split.pace_s_per_500 or float("-inf"))
        metrics["fastest_split"] = {
            "ordinal": work_splits[fastest_idx].split.ordinal,
            "segment_ordinal": work_splits[fastest_idx].segment_ordinal,
            "pace_s_per_500": work_splits[fastest_idx].split.pace_s_per_500,
        }
        metrics["slowest_split"] = {
            "ordinal": work_splits[slowest_idx].split.ordinal,
            "segment_ordinal": work_splits[slowest_idx].segment_ordinal,
            "pace_s_per_500": work_splits[slowest_idx].split.pace_s_per_500,
        }
    else:
        metrics["fastest_split"] = None
        metrics["slowest_split"] = None

    return metrics, notes


def _interval_metrics(workout: Workout) -> tuple[dict | None, dict]:
    """
    Returns (metrics_or_None, data_quality_notes).

    Eligibility is based on having 2+ WORK segments, not on the workout's
    category label - a mixed warmup+intervals+cooldown session has real
    intervals worth analyzing too, and the segment structure (not a
    category tag) is the source of truth per spec section 7.
    """
    work_segs = _work_segments(workout)
    if len(work_segs) < MIN_INTERVALS_FOR_DECAY:
        return None, {
            "interval_analysis_available": False,
            "interval_analysis_unavailable_reason": (
                "This workout doesn't have multiple work intervals to compare."
            ),
        }

    interval_watts: list[float] = []
    interval_paces: list[float] = []
    for seg in work_segs:
        splits_with_watts = [s.watts for s in seg.splits if s.watts is not None]
        splits_with_pace = [s.pace_s_per_500 for s in seg.splits if s.pace_s_per_500 is not None]
        if splits_with_watts:
            interval_watts.append(statistics.mean(splits_with_watts))
        if splits_with_pace:
            interval_paces.append(statistics.mean(splits_with_pace))

    if len(interval_watts) < MIN_INTERVALS_FOR_DECAY:
        return None, {
            "interval_analysis_available": False,
            "interval_analysis_unavailable_reason": (
                "At least 2 work intervals with power data are needed for interval analysis."
            ),
        }

    notes = {"interval_analysis_available": True}

    avg_interval_watts = statistics.mean(interval_watts)
    avg_interval_pace = statistics.mean(interval_paces) if interval_paces else None
    consistency_cv = _coefficient_of_variation_pct(interval_watts)

    best_idx = max(range(len(interval_watts)), key=lambda i: interval_watts[i])
    worst_idx = min(range(len(interval_watts)), key=lambda i: interval_watts[i])

    decay = _linear_regression_decay(interval_watts)
    if len(interval_watts) < NOISY_INTERVAL_COUNT_THRESHOLD:
        decay["noisy_estimate_warning"] = (
            f"Only {len(interval_watts)} intervals are available - decay slope estimates are "
            "noisy with fewer than 5 intervals and should be interpreted cautiously."
        )

    total_work_s = sum(seg.duration_s for seg in work_segs)
    total_rest_s = sum(seg.duration_s for seg in _rest_segments(workout))
    work_rest_ratio = round(total_work_s / total_rest_s, 2) if total_rest_s > 0 else None

    metrics = {
        "n_intervals": len(interval_watts),
        "avg_interval_watts": round(avg_interval_watts, 1),
        "avg_interval_pace_s_per_500": round(avg_interval_pace, 2) if avg_interval_pace else None,
        "avg_interval_pace_display": format_pace(avg_interval_pace) if avg_interval_pace else None,
        "interval_consistency_cv_pct": round(consistency_cv, 2) if consistency_cv is not None else None,
        "best_interval_index": best_idx,
        "best_interval_watts": round(interval_watts[best_idx], 1),
        "worst_interval_index": worst_idx,
        "worst_interval_watts": round(interval_watts[worst_idx], 1),
        "work_rest_ratio": work_rest_ratio,
        "decay": decay,
    }
    return metrics, notes


def _linear_regression_decay(interval_watts: list[float]) -> dict:
    """
    Linear regression of average interval watts against interval index.
    Reports slope (watts per interval), its standard error, and a plain
    -language interpretation. A negative slope means watts are falling
    across the piece (fading); positive means building.
    """
    n = len(interval_watts)
    x = list(range(n))
    x_mean = statistics.mean(x)
    y_mean = statistics.mean(interval_watts)

    ss_xx = sum((xi - x_mean) ** 2 for xi in x)
    if ss_xx == 0:
        return {"slope_watts_per_interval": 0.0, "standard_error": None, "interpretation": "Not enough variation to fit a trend."}

    ss_xy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, interval_watts))
    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean

    if n > 2:
        residuals = [yi - (slope * xi + intercept) for xi, yi in zip(x, interval_watts)]
        residual_ss = sum(r**2 for r in residuals)
        standard_error = (residual_ss / (n - 2)) ** 0.5 / (ss_xx**0.5)
    else:
        standard_error = None

    if slope < -0.5:
        interpretation = "Watts declined across intervals, indicating fade over the course of the piece."
    elif slope > 0.5:
        interpretation = "Watts increased across intervals, indicating a building effort."
    else:
        interpretation = "Watts were roughly stable across intervals, indicating consistent effort."

    return {
        "slope_watts_per_interval": round(slope, 2),
        "standard_error": round(standard_error, 2) if standard_error is not None else None,
        "interpretation": interpretation,
    }


def _generate_insights(
    workout: Workout,
    basic: dict,
    pacing: dict,
    pacing_notes: dict,
    interval_metrics: dict | None,
) -> list[str]:
    insights: list[str] = []

    if pacing_notes.get("pacing_evenness_available") and pacing["pacing_cv_pct"] is not None:
        cv = pacing["pacing_cv_pct"]
        if cv < 3:
            insights.append(f"Power variability was low ({cv:.1f}% CV), indicating consistent pacing.")
        elif cv > 8:
            insights.append(f"Power variability was high ({cv:.1f}% CV), indicating uneven pacing.")

    if pacing_notes.get("pace_fade_available") and pacing["pace_fade_pct"] is not None:
        fade = pacing["pace_fade_pct"]
        if fade > 2:
            insights.append(
                f"Your final quarter was {fade:.1f}% slower than your average pace for this piece."
            )
        elif fade < -2:
            insights.append(
                f"Your final quarter was {abs(fade):.1f}% faster than your average pace - a strong finish."
            )

    if pacing.get("first_half") and pacing.get("second_half"):
        fh = pacing["first_half"]["avg_pace_s_per_500"]
        sh = pacing["second_half"]["avg_pace_s_per_500"]
        if fh and sh:
            diff_pct = ((sh - fh) / fh) * 100.0
            if diff_pct > 1.5:
                insights.append(f"Second half was {diff_pct:.1f}% slower than the first half.")
            elif diff_pct < -1.5:
                insights.append(f"Second half was {abs(diff_pct):.1f}% faster than the first half (negative split).")

    if interval_metrics is not None:
        decay = interval_metrics["decay"]
        if decay.get("slope_watts_per_interval") is not None and decay["slope_watts_per_interval"] < -1.0:
            insights.append(
                f"Average watts fell by about {abs(decay['slope_watts_per_interval']):.1f}W per interval."
            )

    return insights


def compute_watts_per_stroke(workout: Workout, work_splits: list[WorkSplitRef]) -> tuple[dict | None, dict]:
    if workout.avg_watts is None or workout.avg_stroke_rate is None or workout.avg_stroke_rate <= 0:
        return None, {"watts_per_stroke_available": False, "watts_per_stroke_unavailable_reason": "W/stroke requires both average watts and stroke rate."}
    avg = workout.avg_watts / workout.avg_stroke_rate
    splits=[]
    for ref in work_splits:
        if ref.split.watts is not None and ref.split.stroke_rate is not None and ref.split.stroke_rate > 0:
            splits.append({"ordinal": ref.split.ordinal, "segment_ordinal": ref.segment_ordinal, "w_per_stroke": round(ref.split.watts/ref.split.stroke_rate,2)})
    return {"average_w_per_stroke": round(avg,2), "split_values": splits, "note": "W/stroke is watts divided by stroke rate and is a descriptive stroke-efficiency proxy, not direct mechanical work per stroke."}, {"watts_per_stroke_available": True}


def compute_workout_analytics(workout: Workout, athlete=None) -> dict:
    """
    Main entry point. Returns a dict matching the
    {"metrics", "data_quality", "insights"} contract.

    `athlete` is optional because HR-zone analysis needs the athlete's
    max_hr/zone config; when omitted, HR-zone metrics are simply marked
    unavailable rather than the whole call failing. Passed as a plain
    parameter (not imported at module load) to avoid a circular import
    with app.services.hr_zones, which itself imports WorkSplitRef from
    this module.
    """
    work_splits = _flatten_work_splits(workout)

    basic = _basic_metrics(workout, work_splits)

    if workout.has_splits and len(work_splits) >= MIN_SPLITS_FOR_PACING:
        pacing, pacing_notes = _pacing_metrics(work_splits)
    else:
        pacing = {
            "pacing_cv_pct": None,
            "pace_fade_pct": None,
            "first_half": None,
            "second_half": None,
            "fastest_split": None,
            "slowest_split": None,
        }
        pacing_notes = {
            "pacing_evenness_available": False,
            "pacing_evenness_unavailable_reason": "This workout has no split-level data.",
            "pace_fade_available": False,
            "pace_fade_unavailable_reason": "This workout has no split-level data.",
            "half_split_comparison_available": False,
            "half_split_comparison_unavailable_reason": "This workout has no split-level data.",
        }

    interval_metrics, interval_notes = _interval_metrics(workout)

    from app.services.hr_zones import (
        compute_cardiac_decoupling,
        compute_efficiency_factor,
        compute_hr_drift,
        compute_hr_zone_breakdown,
    )

    hr_zones_metrics, hr_zones_notes = (
        compute_hr_zone_breakdown(work_splits, athlete)
        if athlete is not None
        else (None, {"hr_zones_available": False, "hr_zones_unavailable_reason": "No athlete profile provided."})
    )
    efficiency_metrics, efficiency_notes = compute_efficiency_factor(basic)
    wstroke_metrics, wstroke_notes = compute_watts_per_stroke(workout, work_splits)
    decoupling_metrics, decoupling_notes = compute_cardiac_decoupling(workout, work_splits)
    drift_metrics, drift_notes = compute_hr_drift(work_splits, pacing.get("pacing_cv_pct"))

    metrics = {
        "basic": basic,
        "pacing": pacing,
        "intervals": interval_metrics,
        "hr_zones": hr_zones_metrics,
        "efficiency_factor": efficiency_metrics,
        "watts_per_stroke": wstroke_metrics,
        "cardiac_decoupling": decoupling_metrics,
        "hr_drift": drift_metrics,
    }

    data_quality = {
        "has_splits": workout.has_splits,
        "has_power": workout.has_power,
        "has_hr": workout.has_hr,
        "hr_coverage_pct": workout.hr_coverage_pct,
        "has_stroke_rate": workout.has_stroke_rate,
        "split_granularity": workout.split_granularity,
        **pacing_notes,
        **interval_notes,
        **hr_zones_notes,
        **efficiency_notes,
        **wstroke_notes,
        **decoupling_notes,
        **drift_notes,
    }

    insights = _generate_insights(workout, basic, pacing, pacing_notes, interval_metrics)
    insights += _generate_hr_insights(hr_zones_metrics, efficiency_metrics, decoupling_metrics, drift_metrics)

    return {"metrics": metrics, "data_quality": data_quality, "insights": insights}


def _generate_hr_insights(
    hr_zones_metrics: dict | None,
    efficiency_metrics: dict | None,
    decoupling_metrics: dict | None,
    drift_metrics: dict | None,
) -> list[str]:
    insights: list[str] = []

    if decoupling_metrics is not None:
        pct = decoupling_metrics["decoupling_pct"]
        if pct > 5:
            insights.append(
                f"Cardiac decoupling was {pct:.1f}% - your heart rate rose more than power output in "
                "the second half, which can suggest fatigue or heat/hydration effects."
            )
        elif pct < 0:
            insights.append(
                f"Efficiency factor was actually higher in the second half ({abs(pct):.1f}% negative "
                "decoupling), suggesting good aerobic durability for this effort."
            )

    if drift_metrics is not None:
        drift = drift_metrics["drift_pct"]
        if drift > 3:
            insights.append(
                f"Heart rate increased {drift:.1f}% from the first half to the second half while pace "
                "stayed stable, suggesting cardiovascular drift."
            )

    return insights
