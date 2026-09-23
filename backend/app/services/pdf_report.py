from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.athlete import Athlete
from app.models.coach import WorkoutComment
from app.models.workout import Workout
from app.services.performance import compute_personal_bests
from app.services.training_load import (
    build_daily_load_series,
    compute_workout_training_load,
    find_reference_2k_watts,
)
from app.utils.pace import format_pace


ACCENT = colors.HexColor("#2A9D6F")
DARK = colors.HexColor("#131722")
MUTED = colors.HexColor("#667085")
LIGHT = colors.HexColor("#F3F5F7")
BORDER = colors.HexColor("#D9DEE7")
FONT_REGULAR = "OarSightSans"
FONT_BOLD = "OarSightSansBold"

_font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(_font_dir / "Vera.ttf")))
pdfmetrics.registerFont(TTFont(FONT_BOLD, str(_font_dir / "VeraBd.ttf")))
pdfmetrics.registerFontFamily(FONT_REGULAR, normal=FONT_REGULAR, bold=FONT_BOLD)


def _fmt_duration(seconds: float) -> str:
    total = max(int(round(seconds)), 0)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _fmt_distance(metres: float) -> str:
    return f"{metres / 1000:.1f} km" if metres >= 1000 else f"{metres:.0f} m"


def build_athlete_report_pdf(
    *,
    athlete: Athlete,
    workouts: list[Workout],
    all_workouts: list[Workout] | None = None,
    comments: list[WorkoutComment],
    start_date,
    end_date,
    generated_at,
) -> bytes:
    """Build a compact report using the same workout/performance/load services as the API."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=21 * mm,
        bottomMargin=18 * mm,
        title=f"OarSight Athlete Report - {athlete.name}",
        author="OarSight",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName=FONT_BOLD, textColor=DARK, fontSize=22, leading=26, spaceAfter=4))
    styles.add(ParagraphStyle(name="ReportSubtitle", parent=styles["Normal"], fontName=FONT_REGULAR, textColor=MUTED, fontSize=9, leading=13, spaceAfter=14))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName=FONT_BOLD, textColor=DARK, fontSize=12, leading=15, spaceBefore=14, spaceAfter=7))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontName=FONT_REGULAR, textColor=MUTED, fontSize=8, leading=11))
    styles.add(ParagraphStyle(name="Comment", parent=styles["Normal"], fontName=FONT_REGULAR, fontSize=9, leading=13, leftIndent=7, borderColor=BORDER, borderWidth=0.5, borderPadding=7, spaceAfter=7))

    def page_footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
        canvas.setFont(FONT_REGULAR, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 8 * mm, "OarSight - Athlete Performance Report")
        canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    story = [
        Paragraph("OarSight", styles["ReportTitle"]),
        Paragraph(
            f"Athlete Performance Report &nbsp;&nbsp;|&nbsp;&nbsp; {start_date:%d %b %Y} to {end_date:%d %b %Y}",
            styles["ReportSubtitle"],
        ),
    ]

    overview = [
        ["Athlete", escape(athlete.name), "Training level", athlete.training_level.value.title() if athlete.training_level else "Not set"],
        ["Generated", generated_at.strftime("%d %b %Y %H:%M UTC"), "Workouts", str(len(workouts))],
        ["Weight", f"{athlete.weight_kg:.1f} kg" if athlete.weight_kg else "Not set", "2K profile PB", _fmt_duration(athlete.best_2k_seconds) if athlete.best_2k_seconds else "Not set"],
    ]
    overview_table = Table(overview, colWidths=[28 * mm, 55 * mm, 31 * mm, 48 * mm])
    overview_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (2, 0), (2, -1), MUTED),
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
        ("FONTNAME", (1, 0), (1, -1), FONT_BOLD),
        ("FONTNAME", (3, 0), (3, -1), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story += [Paragraph("Athlete overview", styles["Section"]), overview_table]

    pbs = compute_personal_bests(all_workouts if all_workouts is not None else workouts)
    pb_rows = [["Distance", "Time", "Pace", "Date"]]
    for label in ("500m", "1k", "2k", "5k", "6k", "10k"):
        pb = pbs.get(label)
        if not pb:
            continue
        current = pb["current"]
        pb_rows.append([
            label.upper(),
            _fmt_duration(current["duration_s"]),
            f"{current['pace_display']}/500m" if current["pace_display"] else "-",
            current["date"][:10] if current.get("date") else "-",
        ])
    story.append(Paragraph("Personal bests", styles["Section"]))
    story.append(_styled_table(pb_rows, [31 * mm, 39 * mm, 45 * mm, 47 * mm])) if len(pb_rows) > 1 else story.append(Paragraph("No qualifying personal bests are available.", styles["Small"]))

    total_distance = sum(w.total_distance_m for w in workouts)
    total_time = sum(w.total_duration_s for w in workouts)
    reference_watts = find_reference_2k_watts(
        athlete, all_workouts if all_workouts is not None else workouts
    )
    load_pairs = [
        (w.date, compute_workout_training_load(w, athlete, w.avg_hr, reference_watts)["value"])
        for w in workouts
    ]
    load_series = build_daily_load_series(load_pairs)
    latest_load = load_series[-1] if load_series else None
    summary_rows = [
        ["Workouts", str(len(workouts)), "Distance", _fmt_distance(total_distance)],
        ["Training time", _fmt_duration(total_time), "Latest 7-day load", f"{latest_load['rolling_7_day']:.0f}" if latest_load else "-"],
        ["Average distance", _fmt_distance(total_distance / len(workouts)) if workouts else "-", "Latest 28-day load", f"{latest_load['rolling_28_day']:.0f}" if latest_load else "-"],
    ]
    story += [Paragraph("Recent training", styles["Section"]), _styled_table(summary_rows, [35 * mm, 43 * mm, 42 * mm, 42 * mm], header=False)]

    chronological = sorted(workouts, key=lambda w: w.date)
    latest = chronological[-1] if chronological else None
    previous_similar = None
    if latest is not None:
        candidates = [
            workout
            for workout in chronological[:-1]
            if abs(workout.total_distance_m - latest.total_distance_m)
            / max(latest.total_distance_m, 1)
            <= 0.03
        ]
        previous_similar = candidates[-1] if candidates else None

    performance_rows = [["Metric", "Current", "Previous similar"]]
    if latest is not None:
        performance_rows.extend([
            ["Workout", latest.title, previous_similar.title if previous_similar else "-"],
            ["Date", latest.date.strftime("%d %b %Y"), previous_similar.date.strftime("%d %b %Y") if previous_similar else "-"],
            ["Time", _fmt_duration(latest.total_duration_s), _fmt_duration(previous_similar.total_duration_s) if previous_similar else "-"],
            ["Average pace", format_pace(latest.avg_pace_s_per_500) or "-", format_pace(previous_similar.avg_pace_s_per_500) if previous_similar else "-"],
            ["Average watts", f"{latest.avg_watts:.0f} W", f"{previous_similar.avg_watts:.0f} W" if previous_similar else "-"],
        ])
    story.append(Paragraph("Performance comparison", styles["Section"]))
    if latest is not None:
        story.append(_styled_table(performance_rows, [42 * mm, 60 * mm, 60 * mm]))
    else:
        story.append(Paragraph("No workouts are available in this reporting period.", styles["Small"]))

    recent = sorted(workouts, key=lambda w: w.date, reverse=True)[:10]
    workout_rows = [["Date", "Workout", "Distance", "Time", "Pace", "Watts"]]
    for workout in recent:
        workout_rows.append([
            workout.date.strftime("%d %b %Y"),
            Paragraph(escape(workout.title), styles["Small"]),
            _fmt_distance(workout.total_distance_m),
            _fmt_duration(workout.total_duration_s),
            format_pace(workout.avg_pace_s_per_500) or "-",
            f"{workout.avg_watts:.0f}",
        ])
    story += [Paragraph("Recent workouts", styles["Section"]), _styled_table(workout_rows, [25 * mm, 48 * mm, 25 * mm, 24 * mm, 23 * mm, 17 * mm])]

    if comments:
        story.append(Paragraph("Coach comments", styles["Section"]))
        workout_by_id = {w.id: w for w in workouts}
        for comment in comments[-10:]:
            workout = workout_by_id.get(comment.workout_id)
            title = workout.title if workout else "Workout"
            story.append(KeepTogether([
                Spacer(1, 5),
                Paragraph(
                    f"<b>{escape(comment.coach_name_snapshot)}</b> - {escape(title)} - {comment.created_at:%d %b %Y}",
                    styles["Small"],
                ),
                Spacer(1, 7),
                Paragraph(escape(comment.body).replace("\n", "<br/>"), styles["Comment"]),
                Spacer(1, 8),
            ]))

    story += [Spacer(1, 10), Paragraph("This report summarizes recorded training data and is not medical advice or a guarantee of performance.", styles["Small"])]
    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    return buffer.getvalue()


def _styled_table(rows, widths, header: bool = True) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, LIGHT]),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ]
    table.setStyle(TableStyle(commands))
    return table
