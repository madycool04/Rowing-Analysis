"""
Pace <-> watts conversion and averaging rules.

Concept2 power curve:

    W = 2.80 / (t500 / 500)^3

where t500 is seconds per 500m. Watts is the canonical performance value
stored internally (spec section 8); pace is derived from it for display,
and vice versa when only pace is available from a source CSV.

CRITICAL RULE: average pace must NEVER be computed by averaging individual
split paces. It must always be total elapsed time / total distance,
because pace and watts have a nonlinear (cubic) relationship - naive
pace-averaging systematically misrepresents effort. This module is the
single place that rule is implemented so it can't drift between callers.
"""

from __future__ import annotations

C2_CONSTANT = 2.80


def watts_from_pace_per_500(seconds_per_500: float) -> float:
    """Convert a 500m split pace (seconds) to watts via the Concept2 formula."""
    if seconds_per_500 <= 0:
        raise ValueError("seconds_per_500 must be positive")
    return C2_CONSTANT / (seconds_per_500 / 500.0) ** 3


def pace_per_500_from_watts(watts: float) -> float:
    """Inverse conversion: watts -> seconds per 500m."""
    if watts <= 0:
        raise ValueError("watts must be positive")
    return 500.0 * (C2_CONSTANT / watts) ** (1.0 / 3.0)


def average_pace_per_500(total_distance_m: float, total_time_s: float) -> float:
    """
    The ONLY correct way to compute an average pace.

    total elapsed time / total distance, expressed as seconds per 500m.
    Never average individual split paces - see module docstring.
    """
    if total_distance_m <= 0:
        raise ValueError("total_distance_m must be positive")
    if total_time_s <= 0:
        raise ValueError("total_time_s must be positive")
    return (total_time_s / total_distance_m) * 500.0


def average_watts_from_totals(total_distance_m: float, total_time_s: float) -> float:
    """Average watts derived from total time/distance (not from averaging split watts)."""
    return watts_from_pace_per_500(average_pace_per_500(total_distance_m, total_time_s))


def format_pace(seconds_per_500: float | None) -> str | None:
    """Formats a pace in seconds/500m as 'm:ss.t' (e.g. 112.3 -> '1:52.3')."""
    if seconds_per_500 is None:
        return None
    minutes = int(seconds_per_500 // 60)
    seconds = seconds_per_500 - minutes * 60
    return f"{minutes}:{seconds:04.1f}"


def parse_pace_to_seconds(pace_str: str) -> float:
    """
    Parses a pace string like '1:52.3' or '112.3' into seconds.

    Raises ValueError on unparseable input rather than silently
    corrupting data (spec section 9).
    """
    text = pace_str.strip()
    if not text:
        raise ValueError("empty pace string")
    if ":" in text:
        minutes_str, seconds_str = text.split(":", 1)
        return int(minutes_str) * 60 + float(seconds_str)
    return float(text)


def format_duration(total_seconds: float) -> str:
    """Formats a duration in seconds as 'h:mm:ss.t' or 'm:ss.t' if under an hour."""
    hours = int(total_seconds // 3600)
    remainder = total_seconds - hours * 3600
    minutes = int(remainder // 60)
    seconds = remainder - minutes * 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:04.1f}"
    return f"{minutes}:{seconds:04.1f}"
