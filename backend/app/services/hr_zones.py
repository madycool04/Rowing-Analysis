"""
Heart-rate response analytics (spec sections 13-16).

Every function here returns (metrics_or_None, data_quality_notes) and
never fabricates a number when its prerequisites aren't met - callers
merge the notes into the shared data_quality envelope so the reason a
metric is missing is always visible to the athlete.
"""

from __future__ import annotations

from app.models.athlete import DEFAULT_HR_ZONE_CONFIG, Athlete
from app.models.workout import Workout, WorkoutCategory
from app.services.analytics import WorkSplitRef
from app.utils.pace import average_pace_per_500, watts_from_pace_per_500

MIN_DECOUPLING_DURATION_S = 20 * 60
MIN_DECOUPLING_HR_COVERAGE_PCT = 90.0
MIN_DRIFT_SPLITS = 4
MAX_PACING_CV_FOR_DRIFT_PCT = 3.0


def compute_hr_zone_breakdown(work_splits: list[WorkSplitRef], athlete: Athlete) -> tuple[dict | None, dict]:
    if athlete.max_hr is None or athlete.resting_hr is None:
        return None, {
            "hr_zones_available": False,
            "hr_zones_unavailable_reason": "Personalized HR zones require both resting HR and maximum HR in the athlete profile.",
        }
    if athlete.max_hr <= athlete.resting_hr:
        return None, {
            "hr_zones_available": False,
            "hr_zones_unavailable_reason": "Maximum HR must be greater than resting HR.",
        }
    hr_splits = [(r.split.heart_rate, r.split.elapsed_time_s) for r in work_splits if r.split.heart_rate is not None and r.split.elapsed_time_s > 0]
    if not hr_splits:
        return None, {"hr_zones_available": False, "hr_zones_unavailable_reason": "No split-level heart-rate data is available for this workout."}
    boundaries = [(1, "Recovery", .50, .60), (2, "Aerobic", .60, .70), (3, "Tempo", .70, .80), (4, "Threshold", .80, .90), (5, "High intensity", .90, 1.10)]
    hrr = athlete.max_hr - athlete.resting_hr
    def bpm(p): return athlete.resting_hr + p * hrr
    zone_time = {z[0]: 0.0 for z in boundaries}
    covered = 0.0
    for hr,t in hr_splits:
        covered += t
        zone = 5
        for n,_,lo,hi in boundaries:
            if bpm(lo) <= hr < bpm(hi): zone=n; break
        if hr < bpm(.50): zone=1
        zone_time[zone] += t
    result=[]
    for n,label,lo,hi in boundaries:
        result.append({"zone":n,"label":label,"lower_bpm":round(bpm(lo)),"upper_bpm":round(bpm(hi)),"time_s":round(zone_time[n],1),"pct":round(zone_time[n]/covered*100,1)})
    avg=sum(hr*t for hr,t in hr_splits)/covered
    return {"zones":result,"avg_hr":round(avg,1),"max_hr_observed":max(hr for hr,_ in hr_splits),"method":"heart_rate_reserve","resting_hr":athlete.resting_hr,"max_hr":athlete.max_hr}, {"hr_zones_available":True}


def compute_efficiency_factor(basic_metrics: dict) -> tuple[dict | None, dict]:
    avg_watts = basic_metrics.get("avg_watts")
    avg_hr = basic_metrics.get("avg_hr")

    if avg_watts is None or not avg_hr:
        return None, {
            "efficiency_factor_available": False,
            "efficiency_factor_unavailable_reason": (
                "Efficiency factor requires both average watts and average heart rate."
            ),
        }

    ef = avg_watts / avg_hr
    metrics = {
        "efficiency_factor": round(ef, 3),
        "note": (
            "Efficiency factor is a descriptive training metric - most useful for comparing the "
            "same athlete across similar intensity and duration over time. It is not a direct "
            "measure of physiological efficiency."
        ),
    }
    return metrics, {"efficiency_factor_available": True}


def _half_efficiency_factor(half: list[WorkSplitRef]) -> float | None:
    distance = sum(ref.split.distance_m for ref in half)
    duration = sum(ref.split.elapsed_time_s for ref in half)
    hr_pairs = [(ref.split.heart_rate, ref.split.elapsed_time_s) for ref in half if ref.split.heart_rate is not None]

    if distance <= 0 or duration <= 0 or not hr_pairs:
        return None

    hr_time = sum(t for _, t in hr_pairs)
    if hr_time <= 0:
        return None

    avg_hr = sum(hr * t for hr, t in hr_pairs) / hr_time
    if avg_hr <= 0:
        return None

    pace = average_pace_per_500(distance, duration)
    watts = watts_from_pace_per_500(pace)
    return watts / avg_hr


def compute_cardiac_decoupling(workout: Workout, work_splits: list[WorkSplitRef]) -> tuple[dict | None, dict]:
    if workout.category != WorkoutCategory.CONTINUOUS:
        return None, {
            "cardiac_decoupling_available": False,
            "cardiac_decoupling_unavailable_reason": (
                "Cardiac decoupling only applies to continuous efforts, not interval or mixed workouts."
            ),
        }
    if workout.total_duration_s < MIN_DECOUPLING_DURATION_S:
        return None, {
            "cardiac_decoupling_available": False,
            "cardiac_decoupling_unavailable_reason": (
                "Cardiac decoupling requires a continuous effort of at least 20 minutes."
            ),
        }
    if not workout.has_power:
        return None, {
            "cardiac_decoupling_available": False,
            "cardiac_decoupling_unavailable_reason": "Cardiac decoupling requires power data.",
        }

    hr_coverage = workout.hr_coverage_pct or 0.0
    if hr_coverage < MIN_DECOUPLING_HR_COVERAGE_PCT:
        return None, {
            "cardiac_decoupling_available": False,
            "cardiac_decoupling_unavailable_reason": (
                f"Cardiac decoupling requires at least {MIN_DECOUPLING_HR_COVERAGE_PCT:.0f}% heart-rate "
                f"coverage (this workout has {hr_coverage:.0f}%)."
            ),
        }
    if len(work_splits) < 2:
        return None, {
            "cardiac_decoupling_available": False,
            "cardiac_decoupling_unavailable_reason": "Not enough split data to compute cardiac decoupling.",
        }

    midpoint = len(work_splits) // 2
    ef_first = _half_efficiency_factor(work_splits[:midpoint])
    ef_second = _half_efficiency_factor(work_splits[midpoint:])

    if ef_first is None or ef_second is None or ef_first == 0:
        return None, {
            "cardiac_decoupling_available": False,
            "cardiac_decoupling_unavailable_reason": (
                "Could not compute an efficiency factor for both halves of this workout."
            ),
        }

    decoupling_pct = ((ef_first - ef_second) / ef_first) * 100.0
    metrics = {
        "ef_first_half": round(ef_first, 3),
        "ef_second_half": round(ef_second, 3),
        "decoupling_pct": round(decoupling_pct, 2),
        "note": (
            "A commonly cited heuristic in endurance sports treats roughly 5% decoupling as a rough "
            "threshold for aerobic durability. This is a general endurance-sport heuristic, not a "
            "rowing-specific scientific finding, and shouldn't be read as a precise cutoff."
        ),
    }
    return metrics, {"cardiac_decoupling_available": True}


def compute_hr_drift(work_splits: list[WorkSplitRef], pacing_cv_pct: float | None) -> tuple[dict | None, dict]:
    """
    HR drift is only meaningful when pace was stable - otherwise a rising
    HR could simply reflect rising effort, not cardiovascular drift.
    Reuses the watts-based pacing CV already computed for this workout as
    the stability check (spec section 16 leaves the exact CV basis
    unspecified; watts CV is what section 12 recommends for pacing
    evenness generally, so it's reused here for consistency).
    """
    if pacing_cv_pct is None:
        return None, {
            "hr_drift_available": False,
            "hr_drift_unavailable_reason": (
                "HR drift requires pacing consistency data to confirm pace was stable."
            ),
        }
    if pacing_cv_pct > MAX_PACING_CV_FOR_DRIFT_PCT:
        return None, {
            "hr_drift_available": False,
            "hr_drift_unavailable_reason": "HR drift not calculated because pace was not sufficiently stable.",
        }
    if len(work_splits) < MIN_DRIFT_SPLITS:
        return None, {
            "hr_drift_available": False,
            "hr_drift_unavailable_reason": "Not enough splits to compute HR drift.",
        }

    midpoint = len(work_splits) // 2

    def _half_avg_hr(half: list[WorkSplitRef]) -> float | None:
        pairs = [(ref.split.heart_rate, ref.split.elapsed_time_s) for ref in half if ref.split.heart_rate is not None]
        total_t = sum(t for _, t in pairs)
        if not pairs or total_t <= 0:
            return None
        return sum(hr * t for hr, t in pairs) / total_t

    hr_first = _half_avg_hr(work_splits[:midpoint])
    hr_second = _half_avg_hr(work_splits[midpoint:])

    if hr_first is None or hr_second is None or hr_first <= 0:
        return None, {
            "hr_drift_available": False,
            "hr_drift_unavailable_reason": "Insufficient heart-rate data in one or both halves of this workout.",
        }

    drift_pct = ((hr_second / hr_first) - 1.0) * 100.0
    metrics = {
        "first_half_avg_hr": round(hr_first, 1),
        "second_half_avg_hr": round(hr_second, 1),
        "drift_pct": round(drift_pct, 2),
    }
    return metrics, {"hr_drift_available": True}
