"""
Concept2 CSV import.

Handles two shapes of input (spec section 9):

1. Summary CSV - a single aggregate row for the workout (totals only).
   Produces has_splits=False; only totals-based analytics are possible.

2. Detailed CSV - one row per split/interval, as exported by a PM5's
   "detailed results" download. Each row's time/distance/pace/watts/SPM/HR
   describe that split itself (not cumulative). Produces has_splits=True.

Interval workouts are detected by the presence of nonzero per-row rest
columns (rest_time / rest_distance): each source row then becomes a
WORK segment (with its splits) optionally followed by a REST segment.
Continuous workouts (5K, 6K, 10K, 30min, single 2K test) have no rest
columns, so every row becomes a Split inside one single WORK segment.

No separate database logic is needed for intervals vs continuous pieces -
this is exactly the point of the Workout -> Segment -> Split model.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from app.models.segment import SegmentType
from app.models.workout import WorkoutCategory, WorkoutSource
from app.utils.pace import (
    average_pace_per_500,
    parse_pace_to_seconds,
    pace_per_500_from_watts,
    watts_from_pace_per_500,
)
from app.utils.validation import normalize_column_name, safe_float, safe_int, safe_str


logger = logging.getLogger(__name__)


class CSVParseError(Exception):
    """
    Raised when a CSV cannot be safely imported at all (e.g. no
    recognizable columns, empty file, unreadable format). Individual bad
    cells are handled by returning None, not raising - see
    app.utils.validation.
    """


@dataclass
class ParsedSplit:
    ordinal: int
    distance_m: float
    elapsed_time_s: float
    pace_s_per_500: float | None
    watts: float | None
    stroke_rate: float | None
    heart_rate: int | None
    calories: float | None


@dataclass
class ParsedSegment:
    ordinal: int
    type: SegmentType
    start_time_s: float
    duration_s: float
    distance_m: float
    splits: list[ParsedSplit] = field(default_factory=list)


@dataclass
class ParsedWorkout:
    source: WorkoutSource
    category: WorkoutCategory
    title: str
    date: datetime
    total_distance_m: float
    total_duration_s: float
    has_hr: bool
    hr_coverage_pct: float | None
    has_splits: bool
    split_granularity: str | None
    has_power: bool
    has_distance: bool
    has_stroke_rate: bool
    avg_hr: float | None = None
    avg_stroke_rate: float | None = None
    segments: list[ParsedSegment] = field(default_factory=list)


# Candidate normalized-column-name -> canonical field, tried in order.
# Concept2 exports vary between logbook seasons and PM5 firmware
# versions, so several aliases are matched per field.
_COLUMN_ALIASES: dict[str, list[str]] = {
    "date": ["date", "workout_date"],
    "description": ["description", "workout_name", "workout_description", "workout_type", "type"],
    "time": ["time", "work_time", "split_time", "elapsed_time"],
    "distance": ["distance", "meters", "work_distance", "split_distance"],
    "pace": ["pace", "split", "avg_pace", "average_pace", "500m_split"],
    "watts": ["watts", "avg_watts", "average_watts", "power"],
    "spm": ["spm", "stroke_rate", "avg_spm", "average_stroke_rate", "s_m"],
    "hr": ["hr", "heart_rate", "avg_heart_rate", "average_heart_rate", "bpm"],
    "calories": ["calories", "cal", "cal_hr", "total_calories"],
    "rest_time": ["rest_time", "rest_time_s"],
    "rest_distance": ["rest_distance", "rest_distance_m"],
}


def _build_column_map(columns: list[str]) -> dict[str, str]:
    """Maps canonical field name -> actual source column name found in this CSV."""
    normalized_to_original = {normalize_column_name(c): c for c in columns}
    resolved: dict[str, str] = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized_to_original:
                resolved[canonical] = normalized_to_original[alias]
                break
    return resolved


def _extract_pace_and_watts(row: dict, colmap: dict[str, str]) -> tuple[float | None, float | None]:
    """
    Returns (pace_s_per_500, watts), deriving whichever is missing from the
    other via the exact Concept2 conversion. Never fabricates a value when
    both source fields are absent.
    """
    pace = None
    watts = None

    if "pace" in colmap:
        raw = safe_str(row.get(colmap["pace"]))
        if raw is not None:
            try:
                pace = parse_pace_to_seconds(raw)
            except ValueError:
                pace = None

    if "watts" in colmap:
        watts = safe_float(row.get(colmap["watts"]))

    if watts is None and pace is not None and pace > 0:
        watts = watts_from_pace_per_500(pace)
    if pace is None and watts is not None and watts > 0:
        pace = pace_per_500_from_watts(watts)

    return pace, watts


def _parse_time_to_seconds(raw: object) -> float | None:
    """Time cells may be plain seconds or 'mm:ss.t' strings."""
    text = safe_str(raw)
    if text is None:
        return None
    if ":" in text:
        try:
            return parse_pace_to_seconds(text)
        except ValueError:
            return None
    return safe_float(text)


def _parse_date(raw: object) -> datetime | None:
    text = safe_str(raw)
    if text is None:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return pd.to_datetime(text).to_pydatetime()
    except (ValueError, TypeError):
        return None


def parse_concept2_csv(file_bytes: bytes, filename: str | None = None) -> list[ParsedWorkout]:
    """
    Entry point: parses raw CSV bytes into a list of ParsedWorkouts.
    Groups rows by Date and Description to support files containing multiple workouts.

    Raises CSVParseError with a human-readable message on unrecoverable
    problems (spec section 28: "show a useful human-readable error").
    """
    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as exc:  # noqa: BLE001
        raise CSVParseError(
            "This file could not be read as a CSV. Please check the export and try again."
        ) from exc

    if df.empty or len(df.columns) == 0:
        raise CSVParseError("The uploaded CSV file is empty.")

    # Strip any potential leading/trailing spaces from column names
    df.columns = df.columns.str.strip()
    colmap = _build_column_map(list(df.columns))

    if "distance" not in colmap and "time" not in colmap:
        raise CSVParseError(
            "This doesn't look like a Concept2 workout export - no recognizable "
            "distance or time columns were found."
        )

    date_col = colmap.get("date")
    desc_col = colmap.get("description")

    parsed_workouts = []

    # If the file contains columns we can group by, partition the workouts
    if date_col and desc_col:
        for _, group in df.groupby([date_col, desc_col]):
            rows = group.to_dict(orient="records")
            if len(rows) <= 1:
                parsed_workouts.append(_parse_summary(rows[0] if rows else {}, colmap, filename))
            else:
                parsed_workouts.append(_parse_detailed(rows, colmap, filename))
    else:
        # Fallback if there are no date/description columns to group by
        rows = df.to_dict(orient="records")
        logger.info("Concept2 CSV columns=%s rows=%d (no grouping)", list(df.columns), len(rows))
        if len(rows) <= 1:
            parsed_workouts.append(_parse_summary(rows[0] if rows else {}, colmap, filename))
        else:
            parsed_workouts.append(_parse_detailed(rows, colmap, filename))

    return parsed_workouts


def _parse_summary(row: dict, colmap: dict[str, str], filename: str | None) -> ParsedWorkout:
    distance = safe_float(row.get(colmap.get("distance", ""))) or 0.0
    duration = _parse_time_to_seconds(row.get(colmap.get("time", ""))) or 0.0

    if distance <= 0 or duration <= 0:
        raise CSVParseError(
            "The workout summary is missing a valid distance or duration and cannot be imported."
        )

    pace, watts = _extract_pace_and_watts(row, colmap)
    # A summary row's pace/watts, if present, describe the *average* for
    # the whole piece - recompute from totals to guarantee the no-naive-
    # averaging rule holds even if the source file's own average drifted
    # from true total-time/total-distance.
    avg_pace = average_pace_per_500(distance, duration)
    avg_watts = watts if watts is not None else watts_from_pace_per_500(avg_pace)

    hr = safe_int(row.get(colmap.get("hr", "")))
    spm = safe_float(row.get(colmap.get("spm", "")))
    calories = safe_float(row.get(colmap.get("calories", "")))
    date = _parse_date(row.get(colmap.get("date", ""))) or datetime.utcnow()
    description = safe_str(row.get(colmap.get("description", ""))) or f"{int(distance)}m row"

    segment = ParsedSegment(
        ordinal=0,
        type=SegmentType.WORK,
        start_time_s=0.0,
        duration_s=duration,
        distance_m=distance,
        splits=[],  # summary data has no split-level breakdown
    )

    return ParsedWorkout(
        source=WorkoutSource.CONCEPT2_CSV_SUMMARY,
        category=WorkoutCategory.CONTINUOUS,
        title=description,
        date=date,
        total_distance_m=distance,
        total_duration_s=duration,
        has_hr=hr is not None,
        hr_coverage_pct=100.0 if hr is not None else None,
        has_splits=False,
        split_granularity=None,
        has_power=avg_watts is not None,
        has_distance=True,
        has_stroke_rate=spm is not None,
        avg_hr=float(hr) if hr is not None else None,
        avg_stroke_rate=spm,
        segments=[segment],
    )


def _parse_detailed(rows: list[dict], colmap: dict[str, str], filename: str | None) -> ParsedWorkout:
    has_rest_columns = "rest_time" in colmap or "rest_distance" in colmap
    any_rest_nonzero = False
    if has_rest_columns:
        for r in rows:
            rt = safe_float(r.get(colmap.get("rest_time", ""))) or 0.0
            rd = safe_float(r.get(colmap.get("rest_distance", ""))) or 0.0
            if rt > 0 or rd > 0:
                any_rest_nonzero = True
                break

    is_interval = has_rest_columns and any_rest_nonzero

    segments: list[ParsedSegment] = []
    hr_values: list[int] = []
    spm_present = False
    power_present = False
    cumulative_time = 0.0
    total_distance = 0.0

    if is_interval:
        for i, r in enumerate(rows):
            work_distance = safe_float(r.get(colmap.get("distance", ""))) or 0.0
            work_duration = _parse_time_to_seconds(r.get(colmap.get("time", ""))) or 0.0
            pace, watts = _extract_pace_and_watts(r, colmap)
            hr = safe_int(r.get(colmap.get("hr", "")))
            spm = safe_float(r.get(colmap.get("spm", "")))
            calories = safe_float(r.get(colmap.get("calories", "")))

            if hr is not None:
                hr_values.append(hr)
            if spm is not None:
                spm_present = True
            if watts is not None:
                power_present = True

            work_segment = ParsedSegment(
                ordinal=len(segments),
                type=SegmentType.WORK,
                start_time_s=cumulative_time,
                duration_s=work_duration,
                distance_m=work_distance,
                splits=[
                    ParsedSplit(
                        ordinal=0,
                        distance_m=work_distance,
                        elapsed_time_s=work_duration,
                        pace_s_per_500=pace,
                        watts=watts,
                        stroke_rate=spm,
                        heart_rate=hr,
                        calories=calories,
                    )
                ],
            )
            segments.append(work_segment)
            cumulative_time += work_duration
            total_distance += work_distance

            rest_time = safe_float(r.get(colmap.get("rest_time", ""))) or 0.0
            rest_distance = safe_float(r.get(colmap.get("rest_distance", ""))) or 0.0
            if rest_time > 0 or rest_distance > 0:
                rest_segment = ParsedSegment(
                    ordinal=len(segments),
                    type=SegmentType.REST,
                    start_time_s=cumulative_time,
                    duration_s=rest_time,
                    distance_m=rest_distance,
                    splits=[],
                )
                segments.append(rest_segment)
                cumulative_time += rest_time

        first_work_distance = safe_float(rows[0].get(colmap.get("distance", ""))) or 0.0
        title = f"{len(rows)} x {int(first_work_distance)}m intervals"
        category = WorkoutCategory.INTERVAL
        granularity = "interval"

    else:
        splits: list[ParsedSplit] = []
        for i, r in enumerate(rows):
            split_distance = safe_float(r.get(colmap.get("distance", ""))) or 0.0
            split_duration = _parse_time_to_seconds(r.get(colmap.get("time", ""))) or 0.0
            pace, watts = _extract_pace_and_watts(r, colmap)
            hr = safe_int(r.get(colmap.get("hr", "")))
            spm = safe_float(r.get(colmap.get("spm", "")))
            calories = safe_float(r.get(colmap.get("calories", "")))

            if hr is not None:
                hr_values.append(hr)
            if spm is not None:
                spm_present = True
            if watts is not None:
                power_present = True

            splits.append(
                ParsedSplit(
                    ordinal=i,
                    distance_m=split_distance,
                    elapsed_time_s=split_duration,
                    pace_s_per_500=pace,
                    watts=watts,
                    stroke_rate=spm,
                    heart_rate=hr,
                    calories=calories,
                )
            )
            total_distance += split_distance
            cumulative_time += split_duration

        segments = [
            ParsedSegment(
                ordinal=0,
                type=SegmentType.WORK,
                start_time_s=0.0,
                duration_s=cumulative_time,
                distance_m=total_distance,
                splits=splits,
            )
        ]
        title = f"{int(total_distance)}m row"
        category = WorkoutCategory.CONTINUOUS
        granularity = "per_split"

    if total_distance <= 0 or cumulative_time <= 0:
        raise CSVParseError(
            "No valid split rows with both distance and time could be found in this file."
        )

    date = _parse_date(rows[0].get(colmap.get("date", ""))) or datetime.utcnow()
    hr_coverage_pct = (len(hr_values) / len(rows)) * 100.0 if rows else 0.0
    avg_hr, avg_stroke_rate = _weighted_hr_and_spm_from_segments(segments)

    logger.info("Concept2 CSV detected detailed workout: splits=%d segments=%d category=%s", sum(len(x.splits) for x in segments), len(segments), category.value)
    return ParsedWorkout(
        source=WorkoutSource.CONCEPT2_CSV_DETAILED,
        category=category,
        title=title,
        date=date,
        total_distance_m=total_distance,
        total_duration_s=cumulative_time,
        has_hr=len(hr_values) > 0,
        hr_coverage_pct=hr_coverage_pct if hr_values else None,
        has_splits=True,
        split_granularity=granularity,
        has_power=power_present,
        has_distance=True,
        has_stroke_rate=spm_present,
        avg_hr=avg_hr,
        avg_stroke_rate=avg_stroke_rate,
        segments=segments,
    )


def _weighted_hr_and_spm_from_segments(segments: list[ParsedSegment]) -> tuple[float | None, float | None]:
    """Time-weighted average HR/stroke-rate across every split in every segment (work and rest alike)."""
    hr_weighted_sum = 0.0
    hr_weighted_time = 0.0
    spm_weighted_sum = 0.0
    spm_weighted_time = 0.0

    for segment in segments:
        for split in segment.splits:
            if split.heart_rate is not None:
                hr_weighted_sum += split.heart_rate * split.elapsed_time_s
                hr_weighted_time += split.elapsed_time_s
            if split.stroke_rate is not None:
                spm_weighted_sum += split.stroke_rate * split.elapsed_time_s
                spm_weighted_time += split.elapsed_time_s

    avg_hr = hr_weighted_sum / hr_weighted_time if hr_weighted_time > 0 else None
    avg_spm = spm_weighted_sum / spm_weighted_time if spm_weighted_time > 0 else None
    return avg_hr, avg_spm