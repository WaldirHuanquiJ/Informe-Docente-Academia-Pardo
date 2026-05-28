from __future__ import annotations

import re

from app.models import TeacherRecord
from app.services.schedule_utils import TIME_SLOTS, SLOT_START_MINUTES, scheduled_slots_for_teacher_weekday, slot_bounds_minutes, slot_duration_seconds


def teacher_absence_seconds(view, teacher: TeacherRecord) -> int:
    if not view.report or not view.report.period_start:
        return 0
    total = 0
    day_slot_values = view._build_day_slot_values(teacher)
    for day_pos, day in enumerate(view.report.days):
        try:
            weekday = view.report.period_start.replace(day=day).weekday()
        except ValueError:
            continue
        scheduled = scheduled_slots_for_teacher_weekday(
            teacher.teacher_id, teacher.name, teacher.department,
            view._slots_for_day(day), weekday,
        )
        if not scheduled:
            continue
        slot_values = day_slot_values[day_pos]
        for slot_idx in scheduled:
            slot_seconds = slot_duration_seconds(slot_idx)
            if slot_seconds <= 0:
                slot_seconds = view.MIN_VALID_ATTENDANCE_SECONDS
            value = slot_values[slot_idx] if 0 <= slot_idx < len(slot_values) else ""
            if not value.strip():
                total += slot_seconds
            elif view._is_pending_regularization_block(value):
                total += slot_seconds
            elif view._effective_block_seconds(value, slot_idx) < view.MIN_VALID_ATTENDANCE_SECONDS:
                total += slot_seconds
    return total


def teacher_extra_metrics(view, teacher: TeacherRecord) -> tuple[int, int]:
    if not view.report or not view.report.period_start:
        return 0, 0
    total_extra = 0
    total_extra_tardy = 0
    day_slot_values = view._build_day_slot_values(teacher)
    for day_pos, day in enumerate(view.report.days):
        try:
            weekday = view.report.period_start.replace(day=day).weekday()
        except ValueError:
            continue
        scheduled = scheduled_slots_for_teacher_weekday(
            teacher.teacher_id, teacher.name, teacher.department,
            view._slots_for_day(day), weekday,
        )
        slot_values = day_slot_values[day_pos]
        for slot_idx, value in enumerate(slot_values):
            if not value.strip() or slot_idx in scheduled:
                continue
            block_seconds, block_tardy_seconds = view._extra_block_metrics(value)
            if block_seconds < view.MIN_VALID_ATTENDANCE_SECONDS:
                continue
            total_extra += block_seconds
            total_extra_tardy += block_tardy_seconds
    return total_extra, total_extra_tardy


def teacher_early_departure_seconds(view, teacher: TeacherRecord, days: list[int]) -> int:
    if not view.report or not view.report.period_start:
        return 0
    total_minutes = 0
    day_slot_values = view._build_day_slot_values(teacher)
    day_map = {d: day_slot_values[i] for i, d in enumerate(view.report.days)}
    for day in days:
        try:
            weekday = view.report.period_start.replace(day=day).weekday()
        except ValueError:
            continue
        scheduled = scheduled_slots_for_teacher_weekday(
            teacher.teacher_id, teacher.name, teacher.department,
            view._slots_for_day(day), weekday,
        )
        slots = day_map.get(day, [""] * len(TIME_SLOTS))
        for idx in scheduled:
            if not (0 <= idx < len(slots)):
                continue
            value = slots[idx]
            if not value.strip() or view._is_pending_regularization_block(value):
                continue
            total_minutes += view._early_departure_minutes_for_block(value, idx)
    return total_minutes * 60


def teacher_extra_incomplete_seconds(view, teacher: TeacherRecord, days: list[int]) -> int:
    if not view.report or not view.report.period_start:
        return 0
    total_minutes = 0
    day_slot_values = view._build_day_slot_values(teacher)
    day_map = {d: day_slot_values[i] for i, d in enumerate(view.report.days)}
    for day in days:
        try:
            weekday = view.report.period_start.replace(day=day).weekday()
        except ValueError:
            continue
        scheduled = scheduled_slots_for_teacher_weekday(
            teacher.teacher_id, teacher.name, teacher.department,
            view._slots_for_day(day), weekday,
        )
        slots = day_map.get(day, [""] * len(TIME_SLOTS))
        for idx, value in enumerate(slots):
            if idx in scheduled:
                continue
            if not value.strip() or view._is_pending_regularization_block(value):
                continue
            total_minutes += view._extra_early_departure_minutes_for_block(value)
    return total_minutes * 60


def teacher_scheduled_tardiness_seconds(view, teacher: TeacherRecord, days: list[int]) -> int:
    if not view.report or not view.report.period_start:
        return 0
    total = 0
    day_slot_values = view._build_day_slot_values(teacher)
    day_map = {d: day_slot_values[i] for i, d in enumerate(view.report.days)}
    for day in days:
        try:
            weekday = view.report.period_start.replace(day=day).weekday()
        except ValueError:
            continue
        scheduled = scheduled_slots_for_teacher_weekday(
            teacher.teacher_id, teacher.name, teacher.department,
            view._slots_for_day(day), weekday,
        )
        slots = day_map.get(day, [""] * len(TIME_SLOTS))
        for idx in scheduled:
            if not (0 <= idx < len(slots)):
                continue
            value = slots[idx]
            if not value.strip() or view._is_pending_regularization_block(value):
                continue
            if view._effective_block_seconds(value, idx) < view.MIN_VALID_ATTENDANCE_SECONDS:
                continue
            match = re.search(r"([01]?\d|2[0-3]):([0-5]\d)", value or "")
            if not match:
                continue
            entry_min = int(match.group(1)) * 60 + int(match.group(2))
            bounds = slot_bounds_minutes(idx)
            if bounds is None:
                continue
            start_min, _ = bounds
            tardy_seconds = max(entry_min - start_min, 0) * 60
            slot_cap = slot_duration_seconds(idx)
            if slot_cap > 0:
                tardy_seconds = min(tardy_seconds, slot_cap)
            total += tardy_seconds
    return total


def early_departure_minutes_for_block(view, block_text: str, slot_idx: int) -> int:
    bounds = slot_bounds_minutes(slot_idx)
    if bounds is None:
        return 0
    _, slot_end = bounds
    minutes = view._normalized_event_minutes(block_text)
    if len(minutes) < 2:
        return 0
    latest_exit = max(minutes[i + 1] for i in range(0, len(minutes) - 1, 2))
    return max(slot_end - latest_exit, 0)


def extra_early_departure_minutes_for_block(view, block_text: str) -> int:
    minutes = view._normalized_event_minutes(block_text)
    if len(minutes) < 2:
        return 0
    missing = 0
    for i in range(0, len(minutes) - 1, 2):
        entry_real = minutes[i]
        exit_real = minutes[i + 1]
        if exit_real <= entry_real:
            continue
        expected_start = (entry_real // 60) * 60
        next_hour = expected_start + 60
        entry_adjusted = next_hour if (next_hour - entry_real) <= view.EXTRA_EARLY_ROUNDING_MINUTES else entry_real
        expected_end = entry_adjusted + view.EXTRA_BLOCK_MINUTES
        if exit_real < expected_end:
            missing += max(expected_end - exit_real, 0)
    return missing
