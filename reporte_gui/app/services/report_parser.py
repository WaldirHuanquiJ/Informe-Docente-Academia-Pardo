from __future__ import annotations

import calendar
import csv
import re
from datetime import datetime
from pathlib import Path

from app.models import AttendanceReport, TeacherRecord


def _extract_after(tokens: list[str], label: str) -> str:
    for idx, token in enumerate(tokens):
        if token.strip() == label:
            for next_token in tokens[idx + 1 :]:
                clean = next_token.strip()
                if clean:
                    return clean
    return ""


def _days_from_period(period: str) -> list[int]:
    try:
        start_raw = period.split("~")[0].strip()
        start_date = datetime.strptime(start_raw, "%Y-%m-%d")
        month_days = calendar.monthrange(start_date.year, start_date.month)[1]
        return list(range(1, month_days + 1))
    except Exception:
        return []


def parse_period_range(period: str) -> tuple[datetime | None, datetime | None]:
    try:
        start_raw, end_raw = [p.strip() for p in period.split("~", maxsplit=1)]
        return (
            datetime.strptime(start_raw, "%Y-%m-%d"),
            datetime.strptime(end_raw, "%Y-%m-%d"),
        )
    except Exception:
        return None, None


def parse_report(csv_path: Path) -> AttendanceReport:
    rows: list[list[str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file, delimiter=";")
        rows = [row for row in reader]

    if len(rows) < 5:
        raise ValueError("El archivo no tiene el formato esperado")

    period_line = rows[2]
    period = _extract_after(period_line, "Periodo:")
    generated_date = _extract_after(period_line, "Fecha actual:")
    period_start, period_end = parse_period_range(period)

    day_row = rows[3]
    days: list[int] = []
    day_cols: list[int] = []
    for col_idx, token in enumerate(day_row):
        value = token.strip()
        if value.isdigit():
            days.append(int(value))
            day_cols.append(col_idx)

    month_days = _days_from_period(period)
    if month_days:
        if not days or days != month_days[: len(days)]:
            days = month_days
    elif not days:
        days = list(range(1, 32))

    if day_cols:
        start_col = day_cols[0]
        day_columns = [(start_col + offset, day) for offset, day in enumerate(days)]
    else:
        day_columns = list(enumerate(days))

    teachers: list[TeacherRecord] = []
    id_pattern = re.compile(r"^ID:\s*$")

    idx = 4
    while idx < len(rows):
        row = rows[idx]
        if any(id_pattern.match(cell.strip()) for cell in row):
            teacher_id = _extract_after(row, "ID:")
            name = _extract_after(row, "Nombre:")
            department = _extract_after(row, "Departamento:")

            marks: dict[int, str] = {}
            next_idx = idx + 1
            while next_idx < len(rows):
                next_row = rows[next_idx]
                if any(id_pattern.match(cell.strip()) for cell in next_row):
                    break

                for col_idx, day in day_columns:
                    if col_idx >= len(next_row):
                        break
                    mark = next_row[col_idx].strip()
                    if mark:
                        current = marks.get(day)
                        marks[day] = f"{current}, {mark}" if current else mark
                next_idx += 1

            teachers.append(
                TeacherRecord(
                    teacher_id=teacher_id or "-",
                    name=name or "(Sin nombre)",
                    department=department or "(Sin departamento)",
                    marks=marks,
                )
            )
            idx = next_idx
            continue

        idx += 1

    return AttendanceReport(
        period=period or "No detectado",
        generated_date=generated_date or "No detectado",
        days=days,
        teachers=teachers,
        period_start=period_start,
        period_end=period_end,
    )
