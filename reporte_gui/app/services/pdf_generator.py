"""Generador de informe PDF detallado por docente — fondo claro, logo y membrete."""

from __future__ import annotations

import re
import io
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    NextPageTemplate,
    KeepTogether,
    Image as RLImage,
)
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.graphics.charts.barcharts import VerticalBarChart

from app.services.logging_config import get_logger
from app.services.time_rules import (
    compute_seconds_from_mark_text,
    compute_tardiness_seconds_from_mark_text,
    split_cell_blocks,
)

if TYPE_CHECKING:
    from app.models import AttendanceReport, TeacherRecord

logger = get_logger(__name__)

# ── Paleta profesional fondo claro ────────────────────────────────────────
NAVY = colors.HexColor("#111111")
ACCENT_BLUE = colors.HexColor("#1f1f1f")
ACCENT_TEAL = colors.HexColor("#2a2a2a")
ACCENT_AMBER = colors.HexColor("#3a3a3a")
ACCENT_RED = colors.HexColor("#0f0f0f")
ACCENT_PURPLE = colors.HexColor("#2f2f2f")
ACCENT_ROSE = colors.HexColor("#474747")
TEXT_DARK = colors.HexColor("#111111")
TEXT_BODY = colors.HexColor("#141414")
TEXT_MUTED = colors.HexColor("#2b2b2b")
BG_CARD = colors.HexColor("#f3f3f3")
BG_HEADER = colors.HexColor("#d6d6d6")
BG_STRIPE = colors.HexColor("#f1f1f1")
BORDER_LIGHT = colors.HexColor("#777777")
WHITE = colors.white
HEADER_DIVIDER = colors.HexColor("#7a7a7a")
PRINT_BORDER = colors.HexColor("#444444")
PRINT_GRID = colors.HexColor("#666666")
PRINT_HEADER_RULE = colors.HexColor("#262626")

PAGE_W, PAGE_H = A4

# ── Rutas de recursos ─────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LOGO_PATH = _PROJECT_ROOT / "img" / "Logo_white.png"
_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"


def _register_fonts() -> None:
    global _FONT_REGULAR, _FONT_BOLD
    try:
        calibri_path = Path(r"C:\Windows\Fonts\calibri.ttf")
        calibri_bold_path = Path(r"C:\Windows\Fonts\calibrib.ttf")
        if calibri_path.exists() and calibri_bold_path.exists():
            pdfmetrics.registerFont(TTFont("Calibri", str(calibri_path)))
            pdfmetrics.registerFont(TTFont("Calibri-Bold", str(calibri_bold_path)))
            _FONT_REGULAR = "Calibri"
            _FONT_BOLD = "Calibri-Bold"
            return
        arial_path = Path(r"C:\Windows\Fonts\arial.ttf")
        arial_bold_path = Path(r"C:\Windows\Fonts\arialbd.ttf")
        if arial_path.exists() and arial_bold_path.exists():
            pdfmetrics.registerFont(TTFont("Arial", str(arial_path)))
            pdfmetrics.registerFont(TTFont("Arial-Bold", str(arial_bold_path)))
            _FONT_REGULAR = "Arial"
            _FONT_BOLD = "Arial-Bold"
    except Exception:
        _FONT_REGULAR = "Helvetica"
        _FONT_BOLD = "Helvetica-Bold"


def _uc(text: str) -> str:
    return (text or "").upper()


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {
        "title": ParagraphStyle(
            "RPTitle",
            parent=base["Title"],
            fontName=_FONT_BOLD,
            fontSize=26,
            leading=32,
            textColor=NAVY,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "RPSubtitle",
            parent=base["Normal"],
            fontName=_FONT_REGULAR,
            fontSize=12,
            leading=14,
            textColor=TEXT_BODY,
            spaceAfter=4,
            alignment=1,
        ),
        "section": ParagraphStyle(
            "RPSection",
            parent=base["Heading2"],
            fontName=_FONT_BOLD,
            fontSize=14,
            leading=16,
            textColor=ACCENT_BLUE,
            spaceBefore=10,
            spaceAfter=5,
        ),
        "card_label": ParagraphStyle(
            "RPCardLabel",
            parent=base["Normal"],
            fontName=_FONT_BOLD,
            fontSize=7,
            leading=8,
            textColor=TEXT_BODY,
            alignment=1,
        ),
        "card_value": ParagraphStyle(
            "RPCardValue",
            parent=base["Normal"],
            fontName=_FONT_BOLD,
            fontSize=16,
            leading=18,
            textColor=NAVY,
            alignment=1,
        ),
        "body": ParagraphStyle(
            "RPBody",
            parent=base["Normal"],
            fontName=_FONT_REGULAR,
            fontSize=8,
            leading=11,
            textColor=TEXT_DARK,
        ),
        "body_bold": ParagraphStyle(
            "RPBodyBold",
            parent=base["Normal"],
            fontName=_FONT_BOLD,
            fontSize=8,
            leading=11,
            textColor=TEXT_DARK,
        ),
        "footer": ParagraphStyle(
            "RPFooter",
            parent=base["Normal"],
            fontName=_FONT_BOLD,
            fontSize=8,
            leading=10,
            textColor=TEXT_BODY,
            alignment=1,
        ),
    }
    return styles


def _format_hms(total_seconds: int) -> str:
    if total_seconds <= 0:
        return "0h 0m"
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    return f"{h}h {m}m"


def _extract_entry_exit(block_text: str) -> tuple[str, str] | None:
    times = re.findall(r"([01]?\d|2[0-3]):([0-5]\d)", block_text or "")
    if len(times) < 2:
        return None
    return (
        f"{int(times[0][0]):02d}:{int(times[0][1]):02d}",
        f"{int(times[-1][0]):02d}:{int(times[-1][1]):02d}",
    )


def _slot_bounds_minutes_from_index(slot_idx: int) -> tuple[int, int] | None:
    from app.services.schedule_utils import slot_bounds_minutes
    return slot_bounds_minutes(slot_idx)


def _auto_block_text_from_slot(slot_idx: int) -> str:
    bounds = _slot_bounds_minutes_from_index(slot_idx)
    if bounds is None:
        return ""
    start, end = bounds
    return f"{start // 60:02d}:{start % 60:02d}\n{end // 60:02d}:{end % 60:02d}"


def _extract_entry_exit_minutes(block_text: str) -> tuple[int, int] | None:
    times = re.findall(r"([01]?\d|2[0-3]):([0-5]\d)", block_text or "")
    if len(times) < 2:
        return None
    try:
        h1, m1 = int(times[0][0]), int(times[0][1])
        h2, m2 = int(times[-1][0]), int(times[-1][1])
        return h1 * 60 + m1, h2 * 60 + m2
    except Exception:
        return None


def _extract_first_time_minutes(block_text: str) -> int | None:
    times = re.findall(r"([01]?\d|2[0-3]):([0-5]\d)", block_text or "")
    if not times:
        return None
    try:
        return int(times[0][0]) * 60 + int(times[0][1])
    except Exception:
        return None


def _compact_slot_labels(slot_indexes: list[int], time_slots: list[str]) -> str:
    if not slot_indexes:
        return "-"
    ranges: list[tuple[int, int]] = []
    start = slot_indexes[0]
    end = slot_indexes[0]
    for idx in slot_indexes[1:]:
        if idx == end + 1:
            end = idx
        else:
            ranges.append((start, end))
            start = idx
            end = idx
    ranges.append((start, end))
    labels: list[str] = []
    for start_idx, end_idx in ranges:
        start_time = time_slots[start_idx].split("-")[0].strip()
        end_time = time_slots[end_idx].split("-")[1].strip()
        labels.append(f"{start_time}-{end_time}")
    return ", ".join(labels)


def _compute_daily_tardiness_minutes(day_mark: str) -> int:
    return compute_tardiness_seconds_from_mark_text(day_mark) // 60


def _parse_duration_seconds(text: str) -> int:
    raw = (text or "").strip().lower()
    if not raw:
        return 0
    hm = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
    if hm:
        return int(hm.group(1)) * 3600 + int(hm.group(2)) * 60
    hh = re.fullmatch(r"(\d+(?:\.\d+)?)h", raw.replace(" ", ""))
    if hh:
        return int(round(float(hh.group(1)) * 3600))
    mm = re.fullmatch(r"(\d+)m", raw.replace(" ", ""))
    if mm:
        return int(mm.group(1)) * 60
    return 0


def _format_hhmm(total_seconds: int) -> str:
    if total_seconds <= 0:
        return "00:00"
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    return f"{h:02d}:{m:02d}"


def _fit_col_widths_by_content(
    headers: list[str],
    rows: list[list[str]],
    total_width: float,
    min_ratio: float = 0.04,
) -> list[float]:
    if not headers:
        return []
    cols = len(headers)
    min_w = total_width * min_ratio
    weights: list[float] = []
    for c in range(cols):
        h = (headers[c] if c < len(headers) else "").strip()
        max_len = len(h)
        for r in rows:
            if c < len(r):
                max_len = max(max_len, len((r[c] or "").strip()))
        weights.append(max(6.0, float(max_len) + 2.0))

    total = sum(weights) or 1.0
    widths = [(w / total) * total_width for w in weights]

    shortfall = 0.0
    for i, w in enumerate(widths):
        if w < min_w:
            shortfall += (min_w - w)
            widths[i] = min_w
    if shortfall > 0:
        donors = [i for i, w in enumerate(widths) if w > min_w]
        pool = sum(widths[i] - min_w for i in donors)
        if pool > 0:
            for i in donors:
                reducible = widths[i] - min_w
                cut = shortfall * (reducible / pool)
                widths[i] = max(min_w, widths[i] - cut)

    factor = total_width / max(sum(widths), 1e-6)
    return [w * factor for w in widths]


def _build_group_progress_from_daily_rows(
    headers: list[str], rows: list[list[str]]
) -> tuple[list[str], list[float]]:
    if not headers or not rows:
        return [], []
    idx_hours = -1
    idx_in_schedule = -1
    for i, h in enumerate(headers):
        key = (h or "").strip().upper()
        if key.startswith("HORAS"):
            idx_hours = i
        if "EN HORARIO" in key:
            idx_in_schedule = i
    if idx_hours < 0 or idx_in_schedule < 0:
        return [], []

    acc: dict[str, float] = {}
    for row in rows:
        if not row:
            continue
        day_label = (row[0] if len(row) > 0 else "").strip().upper()
        if day_label == "TOTAL":
            continue
        hours_txt = row[idx_hours] if idx_hours < len(row) else ""
        m = re.search(r"(\d+(?:\.\d+)?)", hours_txt or "")
        hours = float(m.group(1)) if m else 0.0
        group_txt = row[idx_in_schedule] if idx_in_schedule < len(row) else ""
        if not group_txt or group_txt.strip() == "-":
            continue
        groups = [g.strip() for g in group_txt.split(",") if g.strip()]
        if not groups:
            continue
        part = hours / len(groups) if hours > 0 else 0.0
        for g in groups:
            acc[g] = acc.get(g, 0.0) + part

    if not acc:
        return [], []
    labels = sorted(acc.keys(), key=lambda x: x.lower())
    values = [acc[k] for k in labels]
    return labels, values


def _build_kpi_card(label: str, value: str, accent: colors.Color, styles: dict, width_cm: float = 4.0) -> Table:
    label_cell = Paragraph(label, styles["card_label"])
    value_cell = Paragraph(value, styles["card_value"])
    tbl = Table([[value_cell], [label_cell]], colWidths=[width_cm * cm], rowHeights=[0.82 * cm, 0.44 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_CARD),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (0, 0), 2),
        ("BOTTOMPADDING", (0, 1), (0, 1), 2),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, accent),
    ]))
    return tbl


def _build_bar_chart(
    title: str, labels: list[str], values: list[float],
    width: float, height: float,
) -> Drawing:
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=WHITE, strokeColor=BORDER_LIGHT, strokeWidth=0.8))

    chart = VerticalBarChart()
    chart.x = 44
    chart.y = 30
    chart.width = width - 72
    chart.height = height - 58
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontName = _FONT_REGULAR
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.fillColor = TEXT_BODY
    chart.categoryAxis.strokeColor = BORDER_LIGHT
    chart.valueAxis.labels.fontName = _FONT_REGULAR
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.labels.fillColor = TEXT_BODY
    chart.valueAxis.strokeColor = BORDER_LIGHT
    chart.bars[0].fillColor = ACCENT_BLUE
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.gridStrokeColor = colors.HexColor("#9a9a9a")
    chart.valueAxis.gridStrokeWidth = 0.6
    chart.bars[0].strokeColor = colors.HexColor("#222222")
    chart.bars[0].strokeWidth = 0.8
    chart.barWidth = max(10, min(20, (width - 92) / max(len(values), 1) - 3))
    chart.groupSpacing = 3
    d.add(chart)

    title_str = String(16, height - 16, title, fontName=_FONT_BOLD, fontSize=10, fillColor=NAVY)
    d.add(title_str)
    return d


def _dashboard_progress_color(percent: float) -> colors.Color:
    p = max(0.0, min(100.0, percent))
    if p >= 100:
        return colors.HexColor("#16a34a")
    if p >= 90:
        return colors.HexColor("#2563eb")
    if p >= 80:
        return colors.HexColor("#eab308")
    if p >= 60:
        return colors.HexColor("#f97316")
    return colors.HexColor("#ef4444")


def _build_teacher_schedule_distribution_chart(rows: list[dict], width: float, height: float) -> Drawing:
    d = Drawing(width, height)
    rows = [r for r in rows if int(r.get("expected", 0) or 0) > 0]
    if not rows:
        d.add(String(width / 2, height / 2, "SIN DATOS POR HORARIO", fontName=_FONT_BOLD, fontSize=9, fillColor=TEXT_MUTED, textAnchor="middle"))
        return d

    rows = sorted(rows, key=lambda r: str(r.get("name", "")).lower())[:8]
    green = colors.HexColor("#16a34a")
    green_dark = colors.HexColor("#166534")
    red = colors.HexColor("#dc2626")
    red_dark = colors.HexColor("#991b1b")
    grid_color = colors.HexColor("#d1d5db")

    left, right = 34, 12
    legend_y = 9
    value_y = 25
    label_y = 36
    bottom, top = 56, 12
    chart_w = width - left - right
    chart_h = height - bottom - top
    slot_w = chart_w / max(len(rows), 1)
    bar_w = max(16, min(30, slot_w * 0.42))
    label_limit = 18 if len(rows) <= 4 else 14

    for pct in (0, 25, 50, 75, 100):
        y = bottom + (pct / 100.0) * chart_h
        d.add(Line(left, y, width - right, y, strokeColor=grid_color, strokeWidth=0.35))
        d.add(String(left - 5, y - 2, f"{pct}%", fontName=_FONT_BOLD, fontSize=6.2, fillColor=TEXT_MUTED, textAnchor="end"))

    for idx, row in enumerate(rows):
        name = str(row.get("name", "") or "Horario").strip()
        attended = int(row.get("attended", 0) or 0)
        debt = int(row.get("debt", 0) or 0)
        if debt <= 0:
            debt = max(int(row.get("expected", 0) or 0) - attended, 0)
        total = max(attended + debt, 1)
        att_pct = max(0.0, min(100.0, (attended / total) * 100.0))
        debt_pct = max(0.0, 100.0 - att_pct)
        x = left + slot_w * idx + slot_w / 2
        y0 = bottom
        att_h = chart_h * (att_pct / 100.0)

        if att_h > 0:
            d.add(Rect(x - bar_w / 2, y0, bar_w, att_h, fillColor=green, strokeColor=green_dark, strokeWidth=0.35))
        if debt_pct > 0:
            d.add(Rect(x - bar_w / 2, y0 + att_h, bar_w, chart_h - att_h, fillColor=red, strokeColor=red_dark, strokeWidth=0.35))

        if att_pct >= 9:
            d.add(String(x, y0 + max(att_h / 2 - 3, 5), f"{att_pct:.0f}%", fontName=_FONT_BOLD, fontSize=6.8, fillColor=WHITE, textAnchor="middle"))
        elif att_pct > 0:
            d.add(String(x, y0 + max(att_h + 5, 8), f"{att_pct:.0f}%", fontName=_FONT_BOLD, fontSize=6.8, fillColor=green_dark, textAnchor="middle"))
        if debt_pct >= 9:
            d.add(String(x, y0 + att_h + max((chart_h - att_h) / 2 - 3, 5), f"{debt_pct:.0f}%", fontName=_FONT_BOLD, fontSize=6.8, fillColor=WHITE, textAnchor="middle"))
        elif debt_pct > 0:
            d.add(String(x, y0 + chart_h + 5, f"{debt_pct:.0f}%", fontName=_FONT_BOLD, fontSize=6.8, fillColor=red_dark, textAnchor="middle"))

        label = name if len(name) <= label_limit else f"{name[:max(label_limit - 1, 8)]}..."
        d.add(String(x, label_y, label, fontName=_FONT_BOLD, fontSize=6.2, fillColor=TEXT_BODY, textAnchor="middle"))
        d.add(String(x, value_y, f"A {_format_hhmm(attended)} | D {_format_hhmm(debt)}", fontName=_FONT_BOLD, fontSize=5.7, fillColor=TEXT_MUTED, textAnchor="middle"))

    legend_x = (width / 2) - 68
    d.add(Rect(legend_x, legend_y - 3, 7, 7, fillColor=green, strokeColor=green_dark, strokeWidth=0.3))
    d.add(String(legend_x + 10, legend_y - 1.5, "Horas asistencia", fontName=_FONT_BOLD, fontSize=6.6, fillColor=TEXT_BODY))
    d.add(Rect(legend_x + 78, legend_y - 3, 7, 7, fillColor=red, strokeColor=red_dark, strokeWidth=0.3))
    d.add(String(legend_x + 88, legend_y - 1.5, "Horas deuda", fontName=_FONT_BOLD, fontSize=6.6, fillColor=TEXT_BODY))
    return d


def _build_teacher_schedule_distribution_table(rows: list[dict], styles: dict, width: float) -> Table:
    headers = ["HORARIO", "ASISTENCIA", "DEUDA", "ASIGNADAS", "% ASIST.", "% DEUDA"]
    data: list[list] = [[Paragraph(h, styles["body_bold"]) for h in headers]]
    clean_rows = [r for r in rows if int(r.get("expected", 0) or 0) > 0]
    for row in sorted(clean_rows, key=lambda r: str(r.get("name", "")).lower()):
        name = str(row.get("name", "") or "Horario").strip()
        attended = int(row.get("attended", 0) or 0)
        debt = int(row.get("debt", 0) or 0)
        expected = int(row.get("expected", 0) or 0)
        if debt <= 0:
            debt = max(expected - attended, 0)
        total = max(attended + debt, 1)
        att_pct = (attended / total) * 100.0 if attended else 0.0
        debt_pct = max(100.0 - att_pct, 0.0) if debt else 0.0
        data.append([
            Paragraph(_uc(name), styles["body"]),
            Paragraph(_format_hhmm(attended), styles["body_bold"]),
            Paragraph(_format_hhmm(debt), styles["body_bold"]),
            Paragraph(_format_hhmm(expected), styles["body"]),
            Paragraph(f"{att_pct:.1f}%", styles["body_bold"]),
            Paragraph(f"{debt_pct:.1f}%", styles["body_bold"]),
        ])
    if len(data) == 1:
        data.append([Paragraph("-", styles["body"])] * len(headers))
    col_widths = [width * 0.34, width * 0.13, width * 0.13, width * 0.14, width * 0.13, width * 0.13]
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), BG_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BOX", (0, 0), (-1, -1), 0.8, PRINT_BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, PRINT_HEADER_RULE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, PRINT_GRID),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, PRINT_GRID),
    ]
    for idx in range(1, len(data)):
        if idx % 2 == 0:
            table_style.append(("BACKGROUND", (0, idx), (-1, idx), BG_STRIPE))
    tbl.setStyle(TableStyle(table_style))
    return tbl


def _build_dashboard_like_daily_progress(
    title: str, labels: list[str], values: list[float], width: float, height: float
) -> Drawing:
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=WHITE, strokeColor=BORDER_LIGHT, strokeWidth=0.8))
    d.add(String(12, height - 14, title, fontName=_FONT_BOLD, fontSize=9, fillColor=NAVY))
    if not values:
        return d

    shown_labels = [str(x) for x in labels[:24]]
    shown_values = [max(0.0, float(v)) for v in values[:31]]
    max_val = max(shown_values) if max(shown_values) > 0 else 1.0
    pct_values = [min(100.0, (v / max_val) * 100.0) for v in shown_values]

    chart = VerticalBarChart()
    chart.x = 46
    chart.y = 34
    chart.width = width - 86
    chart.height = max(96, height - 128)
    chart.data = [pct_values]
    chart.categoryAxis.categoryNames = shown_labels
    chart.categoryAxis.labels.fontName = _FONT_REGULAR
    chart.categoryAxis.labels.fontSize = 5
    chart.categoryAxis.labels.fillColor = TEXT_BODY
    chart.categoryAxis.strokeColor = BORDER_LIGHT
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.valueStep = 20
    chart.valueAxis.labels.fontName = _FONT_REGULAR
    chart.valueAxis.labels.fontSize = 6
    chart.valueAxis.labels.fillColor = TEXT_BODY
    chart.valueAxis.strokeColor = BORDER_LIGHT
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.gridStrokeColor = colors.HexColor("#d1d5db")
    chart.valueAxis.gridStrokeWidth = 0.5
    chart.barWidth = max(6, min(14, (chart.width / max(len(pct_values), 1)) - 2))
    chart.groupSpacing = 2
    chart.bars[0].strokeColor = colors.HexColor("#1f2937")
    chart.bars[0].strokeWidth = 0.3
    chart.bars[0].fillColor = colors.HexColor("#6b7280")
    for idx, _ in enumerate(pct_values):
        try:
            chart.bars[(0, idx)].fillColor = colors.HexColor("#6b7280")
        except Exception:
            pass
    d.add(chart)

    d.add(String(6, chart.y + (chart.height / 2), "% avance", fontName=_FONT_BOLD, fontSize=6, fillColor=TEXT_BODY))
    d.add(String(chart.x + (chart.width / 2) - 20, 14, "Categorias", fontName=_FONT_BOLD, fontSize=6, fillColor=TEXT_BODY))
    # Etiquetas internas con porcentaje por barra.
    for i, pct in enumerate(pct_values):
        try:
            bar = chart.bars[(0, i)]
            bx = float(getattr(bar, "x", 0.0))
            bw = float(getattr(bar, "width", chart.barWidth))
            by = float(getattr(bar, "y", chart.y))
            bh = float(getattr(bar, "height", 0.0))
            tx = bx + (bw / 2.0) - 6
            ty = by + max(2.0, (bh * 0.5) - 3.0)
            d.add(String(tx, ty, f"{pct:.0f}%", fontName=_FONT_BOLD, fontSize=5, fillColor=WHITE))
        except Exception:
            pass
    return d


def _build_matplotlib_progress_chart(
    labels: list[str], values: list[float], width_pt: float, height_pt: float, title: str
):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None

    if not labels or not values:
        return None

    safe_labels = [str(x) for x in labels]
    safe_values = [max(0.0, min(100.0, float(v))) for v in values]
    fig_w_in = max(8.0, width_pt / 72.0)
    fig_h_in = max(3.8, (height_pt / 72.0) * 0.78)
    fig, ax = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=180)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f8fafc")

    x = list(range(len(safe_labels)))
    bars = ax.bar(x, safe_values, color="#6b7280", edgecolor="#111827", linewidth=0.8)

    ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
    ax.set_xlabel("Modalidades / Grupos", fontsize=9, fontweight="bold")
    ax.set_ylabel("% de avance", fontsize=9, fontweight="bold")
    ax.set_ylim(0, 100)
    ax.set_xticks(x)
    ax.set_xticklabels(safe_labels, rotation=18, ha="right", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.45, color="#94a3b8")
    ax.set_axisbelow(True)

    for b, v in zip(bars, safe_values):
        ax.text(
            b.get_x() + b.get_width() / 2,
            max(2.5, v - 5.0),
            f"{v:.0f}%",
            ha="center",
            va="top",
            fontsize=7,
            fontweight="bold",
            color="#ffffff",
        )

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img = RLImage(buf)
    img.drawWidth = width_pt
    img.drawHeight = height_pt
    return img


# ── Callbacks de página ───────────────────────────────────────────────────

def _first_page_bg(canvas, doc) -> None:
    """Fondo blanco + banda superior gris claro con logo."""
    canvas.saveState()
    # Fondo blanco
    canvas.setFillColor(WHITE)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # Banda superior gris claro
    canvas.setFillColor(BG_HEADER)
    canvas.rect(0, PAGE_H - 3.5 * cm, PAGE_W, 3.5 * cm, fill=1, stroke=0)

    # Logo en esquina superior izquierda
    if _LOGO_PATH.exists():
        try:
            img_w = 4.8 * cm
            img_h = 2.0 * cm
            canvas.drawImage(
                str(_LOGO_PATH),
                1.8 * cm,
                PAGE_H - 3.15 * cm,
                width=img_w,
                height=img_h,
                preserveAspectRatio=True,
                anchor="sw",
                mask="auto",
            )
        except Exception:
            pass

    # Texto "INFORME DOCENTE" en la banda
    canvas.setFillColor(NAVY)
    canvas.setFont(_FONT_BOLD, 16)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H - 2.1 * cm, "INFORME DOCENTE")
    canvas.setFont(_FONT_REGULAR, 9)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H - 2.7 * cm, "ACADEMIA PARDO")
    canvas.setStrokeColor(PRINT_HEADER_RULE)
    canvas.setLineWidth(1.6)
    canvas.line(0, PAGE_H - 3.55 * cm, PAGE_W, PAGE_H - 3.55 * cm)

    # Pie de página
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont(_FONT_REGULAR, 7)
    canvas.drawCentredString(PAGE_W / 2, 1.0 * cm, f"REPORTE DOCENTE — ACADEMIA PARDO  |  Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    canvas.setStrokeColor(BORDER_LIGHT)
    canvas.setLineWidth(0.5)
    canvas.line(0, 1.5 * cm, PAGE_W, 1.5 * cm)
    canvas.restoreState()


def _later_pages_bg(canvas, doc) -> None:
    """Fondo blanco + banda delgada con logo pequeño en cabecera."""
    canvas.saveState()
    canvas.setFillColor(WHITE)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # Banda delgada superior
    canvas.setFillColor(BG_HEADER)
    canvas.rect(0, PAGE_H - 1.8 * cm, PAGE_W, 1.8 * cm, fill=1, stroke=0)

    # Logo pequeño en cabecera
    if _LOGO_PATH.exists():
        try:
            canvas.drawImage(
                str(_LOGO_PATH),
                1.8 * cm,
                PAGE_H - 1.62 * cm,
                width=3.0 * cm,
                height=1.25 * cm,
                preserveAspectRatio=True,
                anchor="sw",
                mask="auto",
            )
        except Exception:
            pass

    canvas.setFillColor(NAVY)
    canvas.setFont(_FONT_BOLD, 11)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H - 1.2 * cm, "INFORME DOCENTE — ACADEMIA PARDO")
    canvas.setStrokeColor(PRINT_HEADER_RULE)
    canvas.setLineWidth(1.3)
    canvas.line(0, PAGE_H - 1.85 * cm, PAGE_W, PAGE_H - 1.85 * cm)

    # Pie
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont(_FONT_REGULAR, 7)
    canvas.drawCentredString(PAGE_W / 2, 1.0 * cm, f"ACADEMIA PARDO  |  Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    canvas.setStrokeColor(BORDER_LIGHT)
    canvas.line(0, 1.5 * cm, PAGE_W, 1.5 * cm)
    canvas.restoreState()


# ═══════════════════════════════════════════════════════════════════════════
#  Función principal
# ═══════════════════════════════════════════════════════════════════════════

def generate_teacher_pdf(
    teacher: "TeacherRecord",
    report: "AttendanceReport",
    schedule_slots_per_weekday: dict[int, set[int]],
    extra_seconds: int,
    extra_tardy_seconds: int,
    absence_seconds: int,
    output_path: Path,
    precomputed: dict | None = None,
) -> None:
    if not isinstance(precomputed, dict):
        raise ValueError(
            "PDF debe generarse con payload precomputed desde Informe para "
            "mantener consistencia exacta con Reporte de Asistencia."
        )
    _register_fonts()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = _build_styles()
    table_body_style = ParagraphStyle(
        "RPTableBody",
        parent=styles["body"],
        fontName="Calibri-Bold" if _FONT_BOLD == "Calibri-Bold" else _FONT_BOLD,
        fontSize=7,
        leading=9,
    )
    table_body_bold_style = ParagraphStyle(
        "RPTableBodyBold",
        parent=styles["body_bold"],
        fontName="Calibri-Bold" if _FONT_BOLD == "Calibri-Bold" else _FONT_BOLD,
        fontSize=7,
        leading=9,
    )
    EARLY_ENTRY_ROUNDING_WINDOW_MINUTES = 30
    from app.services.schedule_utils import TIME_SLOTS, SLOT_START_MINUTES, slot_index_for_block, slot_bounds_minutes

    MIN_VALID_ATTENDANCE_SECONDS = 3600
    DUPLICATE_MARK_WINDOW_MINUTES = 20

    def _normalized_event_minutes(block_text: str) -> list[int]:
        times = re.findall(r"([01]?\d|2[0-3]):([0-5]\d)", block_text or "")
        raw: list[int] = []
        for hh, mm in times:
            try:
                raw.append(int(hh) * 60 + int(mm))
            except Exception:
                return []
        if len(raw) <= 1:
            return raw
        normalized: list[int] = []
        idx = 0
        is_entry = True
        while idx < len(raw):
            start = idx
            end = idx
            while end + 1 < len(raw) and (raw[end + 1] - raw[end]) <= DUPLICATE_MARK_WINDOW_MINUTES:
                end += 1
            normalized.append(raw[start] if is_entry else raw[end])
            idx = end + 1
            is_entry = not is_entry
        return normalized

    def _extract_entry_exit_pairs(block_text: str) -> list[tuple[int, int]]:
        minutes = _normalized_event_minutes(block_text)
        if len(minutes) < 2:
            return []
        return [(minutes[i], minutes[i + 1]) for i in range(0, len(minutes) - 1, 2)]

    def _is_pending_regularization_block(block_text: str) -> bool:
        if "PENDIENTE" in (block_text or "").upper():
            return True
        return len(_normalized_event_minutes(block_text)) % 2 == 1

    def _effective_block_seconds(block_text: str, slot_idx: int) -> int:
        bounds = slot_bounds_minutes(slot_idx)
        if bounds is None:
            return compute_seconds_from_mark_text(block_text)
        slot_start, slot_end = bounds
        minutes = _normalized_event_minutes(block_text)
        if len(minutes) < 2:
            return 0
        total = 0
        for i in range(0, len(minutes) - 1, 2):
            entry_min = minutes[i]
            exit_min = minutes[i + 1]
            entry_adjusted = max(entry_min, slot_start)
            exit_adjusted = min(exit_min, slot_end)
            if exit_adjusted <= entry_adjusted:
                continue
            total += (exit_adjusted - entry_adjusted) * 60
        return max(total, 0)

    sorted_days = sorted(report.days)
    day_slot_values: dict[int, list[str]] = {}
    for day in sorted_days:
        slot_values = [""] * len(TIME_SLOTS)
        explicit_slot_sources: dict[int, str] = {}
        for block_text in split_cell_blocks(teacher.marks.get(day, "")):
            slot_idx = slot_index_for_block(block_text)
            if slot_idx is None:
                continue
            if slot_values[slot_idx]:
                slot_values[slot_idx] = f"{slot_values[slot_idx]}\n{block_text}"
            else:
                slot_values[slot_idx] = block_text
            explicit_slot_sources[slot_idx] = block_text

        if report.period_start:
            try:
                weekday = report.period_start.replace(day=day).weekday()
            except ValueError:
                weekday = None
            if weekday is not None:
                scheduled_slots = schedule_slots_per_weekday.get(weekday, set())
                for slot_idx, source_text in list(explicit_slot_sources.items()):
                    pair = _extract_entry_exit_minutes(source_text)
                    if pair is None:
                        continue
                    _, exit_min = pair
                    next_slot = slot_idx + 1
                    if next_slot >= len(TIME_SLOTS):
                        continue
                    if next_slot not in scheduled_slots:
                        continue
                    next_bounds = _slot_bounds_minutes_from_index(next_slot)
                    if next_bounds is None:
                        continue
                    next_start, _ = next_bounds
                    if exit_min != next_start:
                        continue
                    if slot_values[next_slot].strip():
                        continue
                    slot_values[next_slot] = _auto_block_text_from_slot(next_slot)

        day_slot_values[day] = slot_values

    day_mark_map = {day: "\n".join(v for v in day_slot_values[day] if v.strip()) for day in sorted_days}
    total_seconds = 0
    tardiness_seconds = 0
    active_days = len([d for d in report.days if teacher.marks.get(d, "").strip()])

    from app.services.schedule_utils import slot_duration_seconds
    expected_seconds = 0
    for day in sorted_days:
        try:
            if report.period_start:
                weekday = report.period_start.replace(day=day).weekday()
            else:
                continue
        except ValueError:
            continue
        scheduled_slots = set(schedule_slots_per_weekday.get(weekday, set()))
        day_slots = day_slot_values.get(day, [""] * len(TIME_SLOTS))
        for s in scheduled_slots:
            expected_seconds += slot_duration_seconds(s)
            value = day_slots[s] if 0 <= s < len(day_slots) else ""
            total_seconds += _effective_block_seconds(value, s)
            if not value.strip() or _is_pending_regularization_block(value):
                continue
            if _effective_block_seconds(value, s) < MIN_VALID_ATTENDANCE_SECONDS:
                continue
            entry_min = _extract_first_time_minutes(value)
            if entry_min is None or not (0 <= s < len(SLOT_START_MINUTES)):
                continue
            tardy_seconds = max(entry_min - SLOT_START_MINUTES[s], 0) * 60
            slot_cap = slot_duration_seconds(s)
            if slot_cap > 0:
                tardy_seconds = min(tardy_seconds, slot_cap)
            tardiness_seconds += tardy_seconds
        for idx, value in enumerate(day_slots):
            if idx in scheduled_slots or not value.strip():
                continue
            extra_block_seconds = compute_seconds_from_mark_text(value)
            if extra_block_seconds >= MIN_VALID_ATTENDANCE_SECONDS:
                total_seconds += extra_block_seconds

    attendance_pct = (
        min(int((total_seconds / max(expected_seconds, 1)) * 100), 100)
        if expected_seconds
        else 0
    )
    daily_headers_pre: list[str] = []
    daily_rows_pre: list[list[str]] = []
    weekly_headers_pre: list[str] = []
    weekly_rows_pre: list[list[str]] = []
    modality_progress_pre: list[dict] = []
    if isinstance(precomputed, dict):
        metrics = precomputed.get("metrics", {}) or {}
        total_seconds = int(metrics.get("total_hours", total_seconds))
        tardiness_seconds = int(metrics.get("tardiness", tardiness_seconds))
        absence_seconds = int(metrics.get("absence", absence_seconds))
        extra_seconds = int(metrics.get("extra", extra_seconds))
        extra_tardy_seconds = int(metrics.get("extra_tardy", extra_tardy_seconds))
        expected_seconds = int(metrics.get("expected", expected_seconds))
        attendance_pct = int(metrics.get("attendance_pct", attendance_pct))
        active_days = int(metrics.get("active_days", active_days))
        daily_headers_pre = [str(x) for x in (precomputed.get("daily_headers", []) or [])]
        daily_rows_pre = [[str(v) for v in row] for row in (precomputed.get("daily_rows", []) or [])]
        weekly_headers_pre = [str(x) for x in (precomputed.get("weekly_headers", []) or [])]
        weekly_rows_pre = [[str(v) for v in row] for row in (precomputed.get("weekly_rows", []) or [])]
        modality_progress_pre = list(precomputed.get("modality_progress", []) or [])

    # ── Documento ─────────────────────────────────────────────────────────
    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=2.2 * cm,
        bottomMargin=0.0 * cm,
        title=f"Informe Docente — {teacher.name}",
        author="ACADEMIA PARDO",
    )

    first_frame = Frame(
        doc.leftMargin,
        doc.bottomMargin + 1.7 * cm,
        doc.width,
        PAGE_H - (doc.bottomMargin + 1.7 * cm) - (3.9 * cm),
        id="first_main",
    )
    later_frame = Frame(
        doc.leftMargin,
        doc.bottomMargin + 1.7 * cm,
        doc.width,
        PAGE_H - (doc.bottomMargin + 1.7 * cm) - (2.3 * cm),
        id="later_main",
    )
    first_template = PageTemplate(
        id="First",
        frames=[first_frame],
        onPage=_first_page_bg,
        autoNextPageTemplate="Later",
    )
    later_template = PageTemplate(id="Later", frames=[later_frame], onPage=_later_pages_bg)
    doc.addPageTemplates([first_template, later_template])

    story: list = []

    # ── Portada ────────────────────────────────────────────────────────────
    # Espacio para la banda superior (3.5cm) ya aplicado en onPage
    story.append(Spacer(1, 0.3 * cm))

    month_names = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
        7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
    }
    period_str = ""
    period_range_str = (report.period or "").strip()
    if report.period_start:
        m_name = month_names.get(report.period_start.month, "")
        period_str = f"{m_name} {report.period_start.year}"
        try:
            if report.days:
                dmin = min(report.days)
                dmax = max(report.days)
                start_dt = report.period_start.replace(day=dmin)
                end_dt = report.period_start.replace(day=dmax)
                period_range_str = f"{start_dt.strftime('%d/%m/%Y')} - {end_dt.strftime('%d/%m/%Y')}"
        except Exception:
            pass

    story.append(Paragraph(_uc(f"Evaluación de rendimiento docente — {period_str}"), styles["subtitle"]))
    story.append(Spacer(1, 6))

    # ── Datos del docente ─────────────────────────────────────────────────
    info_data = [
        [Paragraph("<b>Docente:</b>", styles["body_bold"]),
         Paragraph(_uc(teacher.name), styles["body"])],
        [Paragraph("<b>ID:</b>", styles["body_bold"]),
         Paragraph(_uc(teacher.teacher_id), styles["body"])],
        [Paragraph("<b>Departamento:</b>", styles["body_bold"]),
         Paragraph(_uc(teacher.department), styles["body"])],
        [Paragraph("<b>Periodo:</b>", styles["body_bold"]),
         Paragraph(_uc(period_range_str), styles["body"])],
        [Paragraph("<b>Fecha de generación:</b>", styles["body_bold"]),
         Paragraph(_uc(datetime.now().strftime("%d/%m/%Y %H:%M")), styles["body"])],
    ]
    info_tbl = Table(info_data, colWidths=[3.8 * cm, 12 * cm])
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_CARD),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 8))

    # ── Resumen KPI ───────────────────────────────────────────────────────
    story.append(Paragraph("RESUMEN EJECUTIVO", styles["section"]))

    schedule_compliance_pct = float(metrics.get("schedule_compliance_pct", attendance_pct) or 0)
    schedule_compliance_text = f"{schedule_compliance_pct:g}%"
    pending_regularization = int(metrics.get("pending_regularization", 0) or 0)
    fulfilled_blocks = int(metrics.get("fulfilled_blocks", 0) or 0)
    scheduled_blocks = int(metrics.get("scheduled_blocks", 0) or 0)
    absence_blocks = int(metrics.get("absence_blocks", 0) or 0)
    early_leave_seconds = int(metrics.get("early_leave", 0) or 0)
    extra_incomplete_seconds = int(metrics.get("extra_incomplete", 0) or 0)
    debt_seconds = int(metrics.get("debt", 0) or 0)
    assigned_seconds = int(metrics.get("expected", 0) or 0)

    kpi_width_cm = ((doc.width / cm) - 0.25) / 7
    kpi_table_data = [
        [
            _build_kpi_card("HORAS ASISTIDAS", _format_hms(total_seconds), ACCENT_BLUE, styles, width_cm=kpi_width_cm),
            _build_kpi_card("COBERTURA NETA", f"{attendance_pct}%", ACCENT_TEAL, styles, width_cm=kpi_width_cm),
            _build_kpi_card("TARDANZA", _format_hms(tardiness_seconds), ACCENT_AMBER, styles, width_cm=kpi_width_cm),
            _build_kpi_card("SALIDA ANTICIPADA", _format_hms(early_leave_seconds), ACCENT_ROSE, styles, width_cm=kpi_width_cm),
            "",
            _build_kpi_card("CUMPLIMIENTO", schedule_compliance_text, ACCENT_TEAL, styles, width_cm=kpi_width_cm),
            _build_kpi_card("PENDIENTES", str(pending_regularization), ACCENT_AMBER, styles, width_cm=kpi_width_cm),
            _build_kpi_card("HORAS ASIGNADAS", _format_hms(assigned_seconds), ACCENT_BLUE, styles, width_cm=kpi_width_cm),
        ],
        [
            _build_kpi_card("HORAS EXTRA", _format_hms(extra_seconds), ACCENT_BLUE, styles, width_cm=kpi_width_cm),
            _build_kpi_card("TARD. EXTRA", _format_hms(extra_tardy_seconds), ACCENT_PURPLE, styles, width_cm=kpi_width_cm),
            _build_kpi_card("EXTRA INCOMPLETA", _format_hms(extra_incomplete_seconds), ACCENT_RED, styles, width_cm=kpi_width_cm),
            _build_kpi_card("HORAS FALTA", _format_hms(absence_seconds), ACCENT_RED, styles, width_cm=kpi_width_cm),
            "",
            _build_kpi_card("HORAS DEUDA", _format_hms(max(debt_seconds, 0)), ACCENT_RED, styles, width_cm=kpi_width_cm),
            _build_kpi_card("BLOQUES", f"{fulfilled_blocks}/{scheduled_blocks}", ACCENT_BLUE, styles, width_cm=kpi_width_cm),
            _build_kpi_card("INASISTENCIAS", str(absence_blocks), ACCENT_RED, styles, width_cm=kpi_width_cm),
        ],
    ]
    kpi_col_widths = [kpi_width_cm * cm] * 4 + [0.25 * cm] + [kpi_width_cm * cm] * 3
    kpi_grid_tbl = Table(kpi_table_data, colWidths=kpi_col_widths)
    kpi_grid_tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (3, 0), 0.8, colors.HexColor("#9ca3af")),
        ("LINEBEFORE", (5, 0), (5, 1), 1.0, colors.HexColor("#9ca3af")),
    ]))
    story.append(KeepTogether([kpi_grid_tbl]))
    story.append(Spacer(1, 8))

    # ── Detalle diario ────────────────────────────────────────────────────
    story.append(Paragraph("DETALLE DIARIO DE ASISTENCIA", styles["section"]))

    weekday_names = {0: "LUN", 1: "MAR", 2: "MIE", 3: "JUE", 4: "VIE", 5: "SAB", 6: "DOM"}
    daily_data = [["DÍA", "SEM.", "ENTRADA", "SALIDA", "HORAS", "TARDANZA", "ESTADO", "EN HORARIO", "FUERA HORARIO"]]
    chart_labels: list[str] = []
    chart_values: list[float] = []
    sunday_row_indices: list[int] = []

    for day in sorted_days:
        mark = day_mark_map.get(day, "")
        day_seconds = 0
        tardy_min = 0
        day_hours = day_seconds / 3600.0
        chart_labels.append(str(day))
        chart_values.append(0.0)

        entry, exit_time = "", ""
        if mark.strip():
            pair = _extract_entry_exit(mark)
            if pair:
                entry, exit_time = pair
        if report.period_start:
            try:
                weekday = report.period_start.replace(day=day).weekday()
                scheduled_slots = sorted(schedule_slots_per_weekday.get(weekday, set()))
            except ValueError:
                scheduled_slots = []
            first_scheduled_mark_idx = next(
                (
                    idx
                    for idx in scheduled_slots
                    if 0 <= idx < len(day_slot_values.get(day, []))
                    and day_slot_values[day][idx].strip()
                ),
                None,
            )
            if first_scheduled_mark_idx is not None:
                entry_min = _extract_first_time_minutes(day_slot_values[day][first_scheduled_mark_idx])
                if entry_min is not None and 0 <= first_scheduled_mark_idx < len(SLOT_START_MINUTES):
                    scheduled_start = SLOT_START_MINUTES[first_scheduled_mark_idx]
                    early_delta = scheduled_start - entry_min
                    if 0 < early_delta <= EARLY_ENTRY_ROUNDING_WINDOW_MINUTES:
                        entry = _uc(f"{scheduled_start // 60:02d}:{scheduled_start % 60:02d}")
                    else:
                        entry = _uc(f"{entry_min // 60:02d}:{entry_min % 60:02d}")
        if not entry and mark.strip():
            first_any_entry = _extract_first_time_minutes(mark)
            if first_any_entry is not None:
                entry = _uc(f"{first_any_entry // 60:02d}:{first_any_entry % 60:02d}")

        try:
            wday = weekday_names.get(report.period_start.replace(day=day).weekday(), "") if report.period_start else ""
        except ValueError:
            wday = ""
        scheduled_slots_for_day: set[int] = set()
        if report.period_start:
            try:
                weekday = report.period_start.replace(day=day).weekday()
                scheduled_slots_for_day = set(schedule_slots_per_weekday.get(weekday, set()))
            except ValueError:
                scheduled_slots_for_day = set()
        slot_values_day = day_slot_values.get(day, [""] * len(TIME_SLOTS))
        scheduled_faltas = 0
        scheduled_pendientes = 0
        tardy_seconds_day = 0
        for idx in scheduled_slots_for_day:
            value = slot_values_day[idx] if 0 <= idx < len(slot_values_day) else ""
            if not value.strip():
                scheduled_faltas += 1
                continue
            if _is_pending_regularization_block(value):
                scheduled_pendientes += 1
                continue
            eff = _effective_block_seconds(value, idx)
            day_seconds += eff
            if eff < MIN_VALID_ATTENDANCE_SECONDS:
                scheduled_faltas += 1
                continue
            entry_min = _extract_first_time_minutes(value)
            if entry_min is not None and 0 <= idx < len(SLOT_START_MINUTES):
                tardy_seconds_day += max(entry_min - SLOT_START_MINUTES[idx], 0) * 60
        for idx, value in enumerate(slot_values_day):
            if idx in scheduled_slots_for_day or not value.strip():
                continue
            extra_block_seconds = compute_seconds_from_mark_text(value)
            if extra_block_seconds >= MIN_VALID_ATTENDANCE_SECONDS:
                day_seconds += extra_block_seconds
        tardy_min = tardy_seconds_day // 60
        day_hours = day_seconds / 3600.0
        chart_values[-1] = day_hours

        marked_slots: set[int] = set()
        for idx, value in enumerate(slot_values_day):
            if not value.strip():
                continue
            if idx in scheduled_slots_for_day:
                marked_slots.add(idx)
                continue
            # Coherente con Informe: extra < 1 hora no se considera.
            if compute_seconds_from_mark_text(value) >= MIN_VALID_ATTENDANCE_SECONDS:
                marked_slots.add(idx)
        in_schedule_slots = sorted(marked_slots.intersection(scheduled_slots_for_day))
        out_schedule_slots = sorted(marked_slots.difference(scheduled_slots_for_day))
        in_schedule_text = _compact_slot_labels(in_schedule_slots, TIME_SLOTS) if in_schedule_slots else "-"
        out_schedule_text = _compact_slot_labels(out_schedule_slots, TIME_SLOTS) if out_schedule_slots else "-"

        any_mark = bool((teacher.marks.get(day, "") or "").strip())
        if not any_mark:
            estado = _uc("FALTA" if scheduled_slots_for_day else "-")
        elif scheduled_slots_for_day and scheduled_pendientes > 0:
            estado = _uc("PENDIENTE")
        elif scheduled_slots_for_day and scheduled_faltas > 0:
            estado = _uc("FALTA")
        elif tardy_min > 0:
            estado = _uc(f"TARDE ({tardy_min} MIN)")
        else:
            estado = _uc("PUNTUAL")

        if estado == _uc("-"):
            row = [
                Paragraph(_uc(str(day)), table_body_style),
                Paragraph(_uc(wday), table_body_style),
                Paragraph(_uc("-"), table_body_style),
                Paragraph(_uc("-"), table_body_style),
                Paragraph(_uc("-"), table_body_bold_style),
                Paragraph(_uc("-"), table_body_style),
                Paragraph(_uc("-"), table_body_bold_style),
                Paragraph(_uc("-"), table_body_style),
                Paragraph(_uc("-"), table_body_style),
            ]
        else:
            row = [
                Paragraph(_uc(str(day)), table_body_style),
                Paragraph(_uc(wday), table_body_style),
                Paragraph(_uc(entry), table_body_style),
                Paragraph(_uc(exit_time), table_body_style),
                Paragraph(_uc(f"{day_hours:.1f}H"), table_body_bold_style),
                Paragraph(_uc(f"{tardy_min}M"), table_body_style) if tardy_min > 0 else Paragraph(_uc("0"), table_body_style),
                Paragraph(estado, table_body_bold_style),
                Paragraph(_uc(in_schedule_text), table_body_style),
                Paragraph(_uc(out_schedule_text), table_body_style),
            ]
        daily_data.append(row)
        if wday == "DOM":
            sunday_row_indices.append(len(daily_data) - 1)

    if daily_rows_pre:
        header = daily_headers_pre if daily_headers_pre else ["DÍA", "SEM.", "ENTRADA", "SALIDA", "HORAS", "TARDANZA", "ESTADO", "SALIDA ANT.", "EXTRA INCOMP.", "TURNOS", "EN HORARIO", "FUERA HORARIO"]
        daily_data = [header]
        chart_labels = []
        chart_values = []
        sunday_row_indices = []
        for row_idx, row_vals in enumerate(daily_rows_pre, start=1):
            row = list(row_vals)[:len(header)]
            while len(row) < len(header):
                row.append("")
            if row and str(row[0]).strip().upper() == "TOTAL":
                row[0] = ""
            rendered = []
            for col_idx, value in enumerate(row):
                style = table_body_bold_style if col_idx == 6 else table_body_style
                rendered.append(Paragraph(_uc(value), style))
            daily_data.append(rendered)
            chart_labels.append(row[0] if row else str(row_idx))
            hours_text = row[4] if len(row) > 4 else "0"
            m = re.search(r"(\d+(?:\.\d+)?)", hours_text)
            chart_values.append(float(m.group(1)) if m else 0.0)
            if len(row) > 1 and row[1].strip().upper() == "DOM":
                sunday_row_indices.append(row_idx)

    # Fila de autosuma al final (coherente con la tabla visible del informe).
    has_total_row = False
    if daily_rows_pre:
        for row_vals in daily_rows_pre:
            if row_vals and str(row_vals[0]).strip().upper() == "TOTAL":
                has_total_row = True
                break
    if len(daily_data) > 1 and not has_total_row:
        total_hours = 0
        total_tardy = 0
        total_early = 0
        total_extra_inc = 0
        for row_idx in range(1, len(daily_data)):
            row_vals = daily_rows_pre[row_idx - 1] if daily_rows_pre and (row_idx - 1) < len(daily_rows_pre) else []
            if row_vals:
                if len(row_vals) > 4:
                    total_hours += _parse_duration_seconds(row_vals[4])
                if len(row_vals) > 5:
                    total_tardy += _parse_duration_seconds(row_vals[5])
                if len(row_vals) > 7:
                    total_early += _parse_duration_seconds(row_vals[7])
                if len(row_vals) > 8:
                    total_extra_inc += _parse_duration_seconds(row_vals[8])
        cols = len(daily_data[0])
        total_row_raw = [""] * cols
        total_row_raw[0] = ""
        if cols > 4:
            total_row_raw[4] = f"{(total_hours / 3600.0):.1f}h"
        if cols > 5:
            total_row_raw[5] = f"{total_tardy // 60}m"
        if cols > 7:
            total_row_raw[7] = _format_hhmm(total_early)
        if cols > 8:
            total_row_raw[8] = _format_hhmm(total_extra_inc)
        total_row = [Paragraph(_uc(v), table_body_bold_style) for v in total_row_raw]
        daily_data.append(total_row)

    avail = doc.width - 0.8 * cm
    if daily_rows_pre:
        daily_headers_text = [str(h) for h in (daily_headers_pre or [])]
        daily_rows_text = [[str(v) for v in row] for row in daily_rows_pre]
    else:
        daily_headers_text = [str(h) for h in daily_data[0]]
        daily_rows_text = []
    daily_col_widths = _fit_col_widths_by_content(
        daily_headers_text,
        daily_rows_text,
        avail,
        min_ratio=0.045,
    )
    # Evita salto de "DOM" en la columna de semana (SEM./SEMANA).
    sem_idx = next((i for i, h in enumerate(daily_headers_text) if str(h).strip().upper().startswith("SEM")), -1)
    if sem_idx >= 0 and sem_idx < len(daily_col_widths):
        min_sem_width = avail * 0.075
        if daily_col_widths[sem_idx] < min_sem_width:
            grow = min_sem_width - daily_col_widths[sem_idx]
            daily_col_widths[sem_idx] = min_sem_width
            donor_idxs = [i for i in range(len(daily_col_widths)) if i != sem_idx and daily_col_widths[i] > (avail * 0.04)]
            donor_pool = sum(daily_col_widths[i] - (avail * 0.04) for i in donor_idxs)
            if donor_pool > 0:
                for i in donor_idxs:
                    reducible = daily_col_widths[i] - (avail * 0.04)
                    cut = grow * (reducible / donor_pool)
                    daily_col_widths[i] = max(avail * 0.04, daily_col_widths[i] - cut)
    daily_tbl = Table(daily_data, colWidths=daily_col_widths, repeatRows=1)
    daily_tbl_style = [
        ("BACKGROUND", (0, 0), (-1, 0), BG_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 1.0, PRINT_BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 1.25, PRINT_HEADER_RULE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.7, PRINT_GRID),
        ("LINEBELOW", (0, 1), (-1, -1), 0.7, PRINT_GRID),
    ]
    for i in range(1, len(daily_data)):
        if i % 2 == 0:
            daily_tbl_style.append(("BACKGROUND", (0, i), (-1, i), BG_STRIPE))
    if len(daily_data) > 1:
        last = len(daily_data) - 1
        daily_tbl_style.append(("BACKGROUND", (0, last), (-1, last), colors.HexColor("#9ca3af")))
        daily_tbl_style.append(("TEXTCOLOR", (0, last), (-1, last), colors.HexColor("#111827")))
        daily_tbl_style.append(("FONTNAME", (0, last), (-1, last), _FONT_BOLD))
        daily_tbl_style.append(("LINEABOVE", (0, last), (-1, last), 1.1, PRINT_HEADER_RULE))
    for i in sunday_row_indices:
        daily_tbl_style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#d1d5db")))
        daily_tbl_style.append(("TEXTCOLOR", (0, i), (-1, i), colors.HexColor("#374151")))
        daily_tbl_style.append(("FONTNAME", (0, i), (-1, i), _FONT_REGULAR))
    daily_tbl.setStyle(TableStyle(daily_tbl_style))
    story.append(daily_tbl)
    story.append(Spacer(1, 8))

    # ── Gráfico ───────────────────────────────────────────────────────────
    # Gráfico de avance retirado por requerimiento.

    # ── Resumen semanal ───────────────────────────────────────────────────
    story.append(Paragraph("RESUMEN SEMANAL", styles["section"]))

    sorted_days = sorted(report.days)
    weeks_data: list[list] = [["SEMANA", "DÍAS", "HORAS TOTALES", "TARDANZA", "RENDIMIENTO"]]
    curr: list[int] = []
    week_idx = 1
    for day in sorted_days:
        if report.period_start:
            try:
                if report.period_start.replace(day=day).weekday() == 6 and curr:
                    weeks_data.append(_build_week_row(week_idx, curr, day_mark_map, styles))
                    week_idx += 1
                    curr = []
            except ValueError:
                pass
        curr.append(day)
    if curr:
        weeks_data.append(_build_week_row(week_idx, curr, day_mark_map, styles))

    if weekly_rows_pre:
        headers = weekly_headers_pre if weekly_headers_pre else ["SEMANA", "DÍAS", "HORAS", "TARDANZA", "RENDIMIENTO"]
        weeks_data = [headers]
        for row_vals in weekly_rows_pre:
            row = list(row_vals)[:len(headers)]
            while len(row) < len(headers):
                row.append("")
            weeks_data.append([Paragraph(_uc(v), table_body_style) for v in row])

    if weekly_rows_pre:
        weekly_headers_text = [str(h) for h in (weekly_headers_pre or [])]
        weekly_rows_text = [[str(v) for v in row] for row in weekly_rows_pre]
    else:
        weekly_headers_text = [str(h) for h in weeks_data[0]]
        weekly_rows_text = []
    weekly_col_widths = _fit_col_widths_by_content(
        weekly_headers_text,
        weekly_rows_text,
        avail,
        min_ratio=0.08,
    )
    week_tbl = Table(weeks_data, colWidths=weekly_col_widths, repeatRows=1)
    week_tbl_style = [
        ("BACKGROUND", (0, 0), (-1, 0), BG_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 1.0, PRINT_BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 1.25, PRINT_HEADER_RULE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.7, PRINT_GRID),
        ("LINEBELOW", (0, 1), (-1, -1), 0.7, PRINT_GRID),
    ]
    for i in range(1, len(weeks_data)):
        if i % 2 == 0:
            week_tbl_style.append(("BACKGROUND", (0, i), (-1, i), BG_STRIPE))
    week_tbl.setStyle(TableStyle(week_tbl_style))
    story.append(week_tbl)

    story.append(Spacer(1, 10))
    if modality_progress_pre:
        story.append(Paragraph("DISTRIBUCION MENSUAL DE ASISTENCIA Y DEUDA", styles["section"]))
        story.append(KeepTogether([
            _build_teacher_schedule_distribution_chart(modality_progress_pre, doc.width, 5.6 * cm),
            Spacer(1, 6),
            _build_teacher_schedule_distribution_table(modality_progress_pre, styles, doc.width),
        ]))
        story.append(Spacer(1, 10))

    story.append(Paragraph(
        f"<i>Informe generado automáticamente por el sistema Reporte Docente — ACADEMIA PARDO. "
        f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}</i>",
        styles["footer"],
    ))

    # ── Build ─────────────────────────────────────────────────────────────
    doc.build(story)
    logger.info("PDF generado: %s", output_path)


def _build_week_row(week_idx: int, days: list[int], day_mark_map: dict[int, str], styles: dict) -> list:
    total_s = sum(compute_seconds_from_mark_text(day_mark_map.get(d, "")) for d in days)
    tardy_s = sum(compute_tardiness_seconds_from_mark_text(day_mark_map.get(d, "")) for d in days)
    expected_week = len(days) * 2 * 3600
    perf = min(int((total_s / max(expected_week, 1)) * 100), 100)
    return [
        Paragraph(_uc(f"Semana {week_idx}"), styles["body_bold"]),
        Paragraph(_uc(f"{min(days)}–{max(days)} ({len(days)} días)"), styles["body"]),
        Paragraph(_format_hms(total_s), styles["body_bold"]),
        Paragraph(_format_hms(tardy_s), styles["body"]),
        Paragraph(_uc(f"{perf}%"), styles["body_bold"]),
    ]
