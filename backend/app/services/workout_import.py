"""
Turns a ParsedWorkout (from the CSV parser) or a manual entry payload into
persisted Workout -> Segment -> Split ORM rows. Kept separate from the
parser itself so parsing (pure, testable, no DB) stays decoupled from
persistence (DB session required).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.segment import Segment, SegmentType
from app.models.split import Split
from app.models.workout import Workout, WorkoutCategory, WorkoutSource
from app.schemas.workout import WorkoutManualCreate
from app.services.csv_parser import ParsedWorkout
from app.utils.pace import average_pace_per_500, watts_from_pace_per_500


def persist_parsed_workout(
    db: Session,
    athlete_id: int,
    parsed: ParsedWorkout,
    filename: str | None = None,
) -> Workout:
    workout = Workout(
        athlete_id=athlete_id,
        source=parsed.source,
        category=parsed.category,
        title=parsed.title,
        date=parsed.date,
        total_distance_m=parsed.total_distance_m,
        total_duration_s=parsed.total_duration_s,
        has_hr=parsed.has_hr,
        hr_coverage_pct=parsed.hr_coverage_pct,
        has_splits=parsed.has_splits,
        split_granularity=parsed.split_granularity,
        has_power=parsed.has_power,
        has_distance=parsed.has_distance,
        has_stroke_rate=parsed.has_stroke_rate,
        avg_hr=parsed.avg_hr,
        avg_stroke_rate=parsed.avg_stroke_rate,
        raw_source_filename=filename,
    )
    db.add(workout)
    db.flush()

    for parsed_segment in parsed.segments:
        segment = Segment(
            workout_id=workout.id,
            ordinal=parsed_segment.ordinal,
            type=parsed_segment.type,
            start_time_s=parsed_segment.start_time_s,
            duration_s=parsed_segment.duration_s,
            distance_m=parsed_segment.distance_m,
        )
        db.add(segment)
        db.flush()

        for parsed_split in parsed_segment.splits:
            db.add(
                Split(
                    segment_id=segment.id,
                    ordinal=parsed_split.ordinal,
                    distance_m=parsed_split.distance_m,
                    elapsed_time_s=parsed_split.elapsed_time_s,
                    pace_s_per_500=parsed_split.pace_s_per_500,
                    watts=parsed_split.watts,
                    stroke_rate=parsed_split.stroke_rate,
                    heart_rate=parsed_split.heart_rate,
                    calories=parsed_split.calories,
                )
            )

    db.commit()
    db.refresh(workout)
    return workout


def persist_manual_workout(db: Session, athlete_id: int, payload: WorkoutManualCreate) -> Workout:
    total_distance = sum(seg.distance_m for seg in payload.segments)
    total_duration = sum(seg.duration_s for seg in payload.segments)

    if payload.category is not None:
        category = payload.category
    elif len(payload.segments) == 1 and payload.segments[0].type == SegmentType.WORK:
        category = WorkoutCategory.CONTINUOUS
    elif any(seg.type != SegmentType.WORK for seg in payload.segments):
        category = WorkoutCategory.MIXED
    else:
        category = WorkoutCategory.INTERVAL

    all_work_splits = [sp for seg in payload.segments if seg.type == SegmentType.WORK for sp in seg.splits]
    all_splits = [sp for seg in payload.segments for sp in seg.splits]
    hr_splits = [sp for sp in all_work_splits if sp.heart_rate is not None]
    sr_splits = [sp for sp in all_work_splits if sp.stroke_rate is not None]
    power_splits = [sp for sp in all_work_splits if sp.watts is not None]

    def weighted(items, value):
        denom = sum(x.elapsed_time_s for x in items)
        return sum(value(x) * x.elapsed_time_s for x in items) / denom if denom else None

    avg_hr = weighted(hr_splits, lambda x: x.heart_rate)
    avg_sr = weighted(sr_splits, lambda x: x.stroke_rate)
    avg_watts = weighted(power_splits, lambda x: x.watts)
    calories = sum(sp.calories or 0 for sp in all_work_splits) or None

    workout = Workout(
        athlete_id=athlete_id, source=WorkoutSource.MANUAL, category=category,
        title=payload.title, date=payload.date, total_distance_m=total_distance,
        total_duration_s=total_duration, has_hr=bool(hr_splits),
        hr_coverage_pct=(sum(x.elapsed_time_s for x in hr_splits) / sum(x.elapsed_time_s for x in all_work_splits) * 100.0) if all_work_splits else None,
        has_splits=len(all_splits) > 1,
        split_granularity=(f"~{round(sum(x.distance_m for x in all_splits)/len(all_splits))}m splits" if all_splits else None),
        has_power=bool(power_splits), has_distance=total_distance > 0, has_stroke_rate=bool(sr_splits),
        avg_hr=avg_hr, avg_stroke_rate=avg_sr, raw_source_filename=None,
    )
    db.add(workout)
    db.flush()

    cumulative_time = 0.0
    for i, seg_input in enumerate(payload.segments, start=1):
        segment = Segment(workout_id=workout.id, ordinal=i, type=seg_input.type,
                          start_time_s=cumulative_time, duration_s=seg_input.duration_s,
                          distance_m=seg_input.distance_m)
        db.add(segment)
        db.flush()
        for sp in seg_input.splits:
            pace = (sp.elapsed_time_s / sp.distance_m) * 500.0
            db.add(Split(segment_id=segment.id, ordinal=sp.ordinal, distance_m=sp.distance_m,
                         elapsed_time_s=sp.elapsed_time_s, pace_s_per_500=pace, watts=sp.watts,
                         stroke_rate=sp.stroke_rate, heart_rate=sp.heart_rate, calories=sp.calories))
        cumulative_time += seg_input.duration_s

    db.commit()
    db.refresh(workout)
    return workout
