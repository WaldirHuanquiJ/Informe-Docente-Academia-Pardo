from __future__ import annotations

import re
from datetime import datetime

from app.services.logging_config import get_logger

logger = get_logger(__name__)

TIME_PATTERN = re.compile(r"([01]?\d|2[0-3]):[0-5]\d")
ALLOWED_ROUNDED_HOURS = [9, 11, 13, 14, 16, 18, 20]
ENTRY_SCHEDULE_MINUTES = [7 * 60, 9 * 60, 11 * 60, 14 * 60, 16 * 60, 18 * 60]
ENTRY_ROUNDING_TOLERANCE_MIN = 20
CONTINUOUS_GAP_TOLERANCE_MIN = 20


def normalize_time_marks(raw_text: str) -> str:
    compact = raw_text.replace(" ", "")
    found = [m.group(0) for m in TIME_PATTERN.finditer(compact)]
    if found:
        completed = reconcile_entries_and_exits(found)
        return format_time_blocks(completed)
    return raw_text


def reconcile_entries_and_exits(times: list[str]) -> list[str]:
    if not times:
        return times

    normalized: list[str] = []
    parsed_times: list[datetime] = []
    for t in times:
        try:
            parsed_times.append(datetime.strptime(t, "%H:%M"))
        except ValueError:
            return times

    idx = 0
    while idx < len(parsed_times):
        entry_dt = parsed_times[idx]
        normalized.append(times[idx])

        expected_hour = nearest_allowed_hour((entry_dt.hour + 2) % 24)
        expected_minutes = expected_hour * 60

        if idx + 1 < len(parsed_times):
            next_dt = parsed_times[idx + 1]
            next_minutes = next_dt.hour * 60 + next_dt.minute
            next_rounded_entry = rounded_entry_if_close(next_minutes)
            if (
                next_rounded_entry is not None
                and abs(next_minutes - expected_minutes) <= ENTRY_ROUNDING_TOLERANCE_MIN
            ):
                normalized.append(f"{expected_hour:02d}:00")
                idx += 1
                continue
            if abs(next_minutes - expected_minutes) <= 30:
                normalized.append(times[idx + 1])
                idx += 2
                continue

        normalized.append(f"{expected_hour:02d}:00")
        idx += 1

    return adjust_continuous_schedule(normalized)


def adjust_continuous_schedule(times: list[str]) -> list[str]:
    if len(times) < 4:
        return times

    adjusted = list(times)
    for idx in range(2, len(adjusted), 2):
        prev_exit = adjusted[idx - 1]
        current_entry = adjusted[idx]
        try:
            prev_dt = datetime.strptime(prev_exit, "%H:%M")
            curr_dt = datetime.strptime(current_entry, "%H:%M")
        except ValueError:
            continue

        prev_minutes = prev_dt.hour * 60 + prev_dt.minute
        curr_minutes = curr_dt.hour * 60 + curr_dt.minute
        gap = curr_minutes - prev_minutes
        if 0 <= gap <= CONTINUOUS_GAP_TOLERANCE_MIN:
            adjusted[idx] = prev_exit

    return adjusted


def format_time_blocks(times: list[str]) -> str:
    if not times:
        return ""

    lines: list[str] = []
    for idx, value in enumerate(times):
        lines.append(value)
        if idx % 2 == 1 and idx < len(times) - 1:
            lines.append("_____")
    return "\n".join(lines)


def nearest_allowed_hour(target_hour: int) -> int:
    return min(ALLOWED_ROUNDED_HOURS, key=lambda h: abs(h - target_hour))


def rounded_entry_if_close(actual_minutes: int) -> int | None:
    closest = min(ENTRY_SCHEDULE_MINUTES, key=lambda m: abs(m - actual_minutes))
    if abs(actual_minutes - closest) <= ENTRY_ROUNDING_TOLERANCE_MIN:
        return closest // 60
    return None


def split_cell_blocks(cell_value: str) -> list[str]:
    if not cell_value.strip():
        return [""]
    raw_blocks = [part.strip() for part in cell_value.split("_____")]
    blocks = ["\n".join(line.strip() for line in part.splitlines() if line.strip()) for part in raw_blocks]
    cleaned = [b for b in blocks if b]
    return cleaned or [""]


def compute_seconds_from_mark_text(mark_text: str) -> int:
    times = [m.group(0) for m in TIME_PATTERN.finditer(mark_text)]
    if len(times) < 2:
        return 0

    total = 0
    for idx in range(0, len(times) - 1, 2):
        entry = datetime.strptime(times[idx], "%H:%M")
        exit_ = datetime.strptime(times[idx + 1], "%H:%M")
        delta = int((exit_ - entry).total_seconds())
        if delta < 0:
            delta += 24 * 3600
        total += delta
    return total


def expected_entry_minutes(actual_minutes: int) -> int | None:
    candidates = [m for m in ENTRY_SCHEDULE_MINUTES if m <= actual_minutes]
    if not candidates:
        return None
    return candidates[-1]


def compute_tardiness_seconds_from_mark_text(mark_text: str) -> int:
    times = [m.group(0) for m in TIME_PATTERN.finditer(mark_text)]
    if not times:
        return 0

    tardiness = 0
    for idx in range(0, len(times), 2):
        entry = datetime.strptime(times[idx], "%H:%M")
        entry_minutes = entry.hour * 60 + entry.minute
        expected = expected_entry_minutes(entry_minutes)
        if expected is None:
            continue
        delay_minutes = entry_minutes - expected
        if delay_minutes > 0:
            tardiness += delay_minutes * 60
    return tardiness
