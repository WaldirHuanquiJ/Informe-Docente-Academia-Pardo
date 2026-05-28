from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisPolicy:
    min_valid_attendance_minutes: int = 45
    duplicate_mark_window_minutes: int = 20
    extra_early_rounding_minutes: int = 30
    extra_block_minutes: int = 120

    @property
    def min_valid_attendance_seconds(self) -> int:
        return self.min_valid_attendance_minutes * 60


DEFAULT_POLICY = AnalysisPolicy()


_TIME_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")


def normalized_event_minutes(block_text: str, *, duplicate_window_minutes: int) -> list[int]:
    times = _TIME_RE.findall(block_text or "")
    raw_minutes: list[int] = []
    for hh, mm in times:
        try:
            raw_minutes.append(int(hh) * 60 + int(mm))
        except Exception:
            return []
    if len(raw_minutes) <= 1:
        return raw_minutes

    normalized: list[int] = []
    idx = 0
    is_entry_event = True
    while idx < len(raw_minutes):
        cluster_start = idx
        cluster_end = idx
        while cluster_end + 1 < len(raw_minutes):
            if raw_minutes[cluster_end + 1] - raw_minutes[cluster_end] <= duplicate_window_minutes:
                cluster_end += 1
            else:
                break
        normalized.append(raw_minutes[cluster_start] if is_entry_event else raw_minutes[cluster_end])
        idx = cluster_end + 1
        is_entry_event = not is_entry_event
    return normalized


def extract_entry_exit_pairs(block_text: str, *, duplicate_window_minutes: int) -> list[tuple[int, int]]:
    minutes = normalized_event_minutes(block_text, duplicate_window_minutes=duplicate_window_minutes)
    if len(minutes) < 2:
        return []
    return [(minutes[i], minutes[i + 1]) for i in range(0, len(minutes) - 1, 2)]


def extract_trailing_unpaired_entry_minutes(
    block_text: str, *, duplicate_window_minutes: int
) -> int | None:
    minutes = normalized_event_minutes(block_text, duplicate_window_minutes=duplicate_window_minutes)
    if len(minutes) < 3 or len(minutes) % 2 == 0:
        return None
    return minutes[-1]


def extract_single_entry_minutes(block_text: str, *, duplicate_window_minutes: int) -> int | None:
    minutes = normalized_event_minutes(block_text, duplicate_window_minutes=duplicate_window_minutes)
    if len(minutes) != 1:
        return None
    return minutes[0]


def extra_planned_window(
    entry_real: int,
    exit_real: int,
    *,
    extra_early_rounding_minutes: int,
    extra_block_minutes: int,
) -> tuple[int, int, int, int] | None:
    if exit_real <= entry_real:
        return None
    base_start = (entry_real // 60) * 60
    next_hour = base_start + 60
    scheduled_start = (
        next_hour
        if (next_hour - entry_real) <= extra_early_rounding_minutes
        else base_start
    )
    entry_adjusted = max(entry_real, scheduled_start)
    tardy_seconds = max(entry_real - scheduled_start, 0) * 60
    observed = max(exit_real - scheduled_start, 0)
    blocks = max(1, int(round(observed / float(extra_block_minutes))))
    expected_end = scheduled_start + (blocks * extra_block_minutes)
    exit_adjusted = min(exit_real, expected_end)
    if exit_adjusted <= entry_adjusted:
        return None
    return entry_adjusted, tardy_seconds, expected_end, exit_adjusted


def extra_block_metrics(
    block_text: str,
    *,
    duplicate_window_minutes: int,
    extra_early_rounding_minutes: int,
    extra_block_minutes: int,
) -> tuple[int, int]:
    minutes = normalized_event_minutes(block_text, duplicate_window_minutes=duplicate_window_minutes)
    if len(minutes) < 2:
        return 0, 0

    total_seconds = 0
    total_tardy_seconds = 0
    for idx in range(0, len(minutes) - 1, 2):
        plan = extra_planned_window(
            minutes[idx],
            minutes[idx + 1],
            extra_early_rounding_minutes=extra_early_rounding_minutes,
            extra_block_minutes=extra_block_minutes,
        )
        if plan is None:
            continue
        entry_adjusted, tardy_seconds, _expected_end, exit_adjusted = plan
        total_seconds += (exit_adjusted - entry_adjusted) * 60
        total_tardy_seconds += tardy_seconds
    return total_seconds, total_tardy_seconds


def normalize_extra_block_text(
    block_text: str,
    *,
    duplicate_window_minutes: int,
    extra_early_rounding_minutes: int,
    extra_block_minutes: int,
) -> str:
    minutes = normalized_event_minutes(block_text, duplicate_window_minutes=duplicate_window_minutes)
    if len(minutes) < 2:
        return block_text
    lines: list[str] = []
    for idx in range(0, len(minutes) - 1, 2):
        plan = extra_planned_window(
            minutes[idx],
            minutes[idx + 1],
            extra_early_rounding_minutes=extra_early_rounding_minutes,
            extra_block_minutes=extra_block_minutes,
        )
        if plan is None:
            continue
        entry_adjusted, _tardy_seconds, _expected_end, exit_adjusted = plan
        lines.append(f"{entry_adjusted // 60:02d}:{entry_adjusted % 60:02d}")
        lines.append(f"{exit_adjusted // 60:02d}:{exit_adjusted % 60:02d}")
    return "\n".join(lines) if lines else block_text
