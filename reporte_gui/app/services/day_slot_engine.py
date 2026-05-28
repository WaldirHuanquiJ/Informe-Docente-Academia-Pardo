from __future__ import annotations

from app.models import TeacherRecord
from app.services.attendance_engine import (
    extract_entry_exit_pairs,
    extract_single_entry_minutes,
    extract_trailing_unpaired_entry_minutes,
    normalize_extra_block_text,
)
from app.services.schedule_utils import slot_bounds_minutes, slot_index_for_block
from app.services.time_rules import split_cell_blocks


def _append_slot_value(slot_values: list[str], slot_idx: int, text: str) -> None:
    if not (0 <= slot_idx < len(slot_values)):
        return
    value = (text or "").strip()
    if not value:
        return
    current = (slot_values[slot_idx] or "").strip()
    if not current:
        slot_values[slot_idx] = value
        return
    existing_blocks = split_cell_blocks(current)
    if value in existing_blocks:
        return
    slot_values[slot_idx] = f"{current}\n_____\n{value}"


def _scheduled_slot_for_entry_minute(
    scheduled_slots: set[int],
    minute_value: int,
    *,
    early_punctual_window_minutes: int,
) -> int | None:
    ordered_slots = sorted(scheduled_slots)
    if not ordered_slots:
        return None

    for slot_idx in ordered_slots:
        bounds = slot_bounds_minutes(slot_idx)
        if bounds is None:
            continue
        start_min, _ = bounds
        if (start_min - early_punctual_window_minutes) <= minute_value <= start_min:
            return slot_idx

    for slot_idx in ordered_slots:
        bounds = slot_bounds_minutes(slot_idx)
        if bounds is None:
            continue
        start_min, end_min = bounds
        if start_min <= minute_value < end_min:
            return slot_idx

    best_slot = None
    best_distance = None
    for slot_idx in ordered_slots:
        bounds = slot_bounds_minutes(slot_idx)
        if bounds is None:
            continue
        start_min, _ = bounds
        distance = abs(minute_value - start_min)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_slot = slot_idx
    return best_slot


def build_day_slot_values(
    *,
    teacher: TeacherRecord,
    days: list[int],
    report_rows_per_teacher: int,
    duplicate_mark_window_minutes: int,
    extra_early_rounding_minutes: int,
    extra_block_minutes: int,
    min_valid_attendance_minutes: int,
    early_punctual_window_minutes: int,
    scheduled_slots_for_day,
) -> list[list[str]]:
    result: list[list[str]] = []
    for day in days:
        slot_values = [""] * report_rows_per_teacher
        scheduled_slots = scheduled_slots_for_day(day)
        mark_text = teacher.marks.get(day)
        if mark_text is None:
            mark_text = teacher.marks.get(str(day), "")
        blocks = split_cell_blocks(mark_text or "")
        for block_text in blocks:
            pairs = extract_entry_exit_pairs(
                block_text,
                duplicate_window_minutes=duplicate_mark_window_minutes,
            )
            if not pairs:
                pending_minutes = extract_single_entry_minutes(
                    block_text,
                    duplicate_window_minutes=duplicate_mark_window_minutes,
                )
                if pending_minutes is not None:
                    pending_slot = _scheduled_slot_for_entry_minute(
                        scheduled_slots,
                        pending_minutes,
                        early_punctual_window_minutes=early_punctual_window_minutes,
                    )
                    if pending_slot is not None:
                        pending_time = f"{pending_minutes // 60:02d}:{pending_minutes % 60:02d}"
                        if pending_slot in scheduled_slots:
                            bounds = slot_bounds_minutes(pending_slot)
                            if bounds is not None:
                                slot_start, _slot_end = bounds
                                if pending_minutes <= slot_start and (slot_start - pending_minutes) <= early_punctual_window_minutes:
                                    pending_time = f"{slot_start // 60:02d}:{slot_start % 60:02d}"
                        else:
                            adjusted = (
                                ((pending_minutes // 60) + 1) * 60
                                if ((((pending_minutes // 60) + 1) * 60) - pending_minutes) <= extra_early_rounding_minutes
                                else pending_minutes
                            )
                            pending_time = f"{adjusted // 60:02d}:{adjusted % 60:02d}"
                        _append_slot_value(slot_values, pending_slot, f"PENDIENTE\n{pending_time}")
                        continue
                slot_idx = slot_index_for_block(block_text)
                if slot_idx is None:
                    continue
                pending_label = "PENDIENTE"
                if pending_minutes is not None:
                    adjusted = (
                        ((pending_minutes // 60) + 1) * 60
                        if ((((pending_minutes // 60) + 1) * 60) - pending_minutes) <= extra_early_rounding_minutes
                        else pending_minutes
                    )
                    pending_label = f"PENDIENTE\n{adjusted // 60:02d}:{adjusted % 60:02d}"
                _append_slot_value(slot_values, slot_idx, pending_label)
                continue

            trailing_pending = extract_trailing_unpaired_entry_minutes(
                block_text,
                duplicate_window_minutes=duplicate_mark_window_minutes,
            )
            if trailing_pending is not None:
                pending_slot = _scheduled_slot_for_entry_minute(
                    scheduled_slots,
                    trailing_pending,
                    early_punctual_window_minutes=early_punctual_window_minutes,
                )
                if pending_slot is not None:
                    _append_slot_value(
                        slot_values,
                        pending_slot,
                        f"PENDIENTE\n{trailing_pending // 60:02d}:{trailing_pending % 60:02d}",
                    )

            any_assigned = False
            for entry_min, exit_min in pairs:
                if exit_min <= entry_min:
                    continue
                assigned = False
                covered: list[tuple[int, int]] = []
                for slot_idx in sorted(scheduled_slots):
                    bounds = slot_bounds_minutes(slot_idx)
                    if bounds is None:
                        continue
                    slot_start, slot_end = bounds
                    overlap_start = max(entry_min, slot_start)
                    overlap_end = min(exit_min, slot_end)
                    if overlap_end <= overlap_start:
                        continue
                    overlap_text = (
                        f"{overlap_start // 60:02d}:{overlap_start % 60:02d}\n"
                        f"{overlap_end // 60:02d}:{overlap_end % 60:02d}"
                    )
                    _append_slot_value(slot_values, slot_idx, overlap_text)
                    covered.append((overlap_start, overlap_end))
                    assigned = True
                    any_assigned = True
                if assigned:
                    covered.sort(key=lambda x: x[0])
                    merged_cov: list[tuple[int, int]] = []
                    for c_start, c_end in covered:
                        if not merged_cov or c_start > merged_cov[-1][1]:
                            merged_cov.append((c_start, c_end))
                        else:
                            prev_start, prev_end = merged_cov[-1]
                            merged_cov[-1] = (prev_start, max(prev_end, c_end))
                    cursor = entry_min
                    for c_start, c_end in merged_cov:
                        if cursor < c_start:
                            if (c_start - cursor) <= early_punctual_window_minutes:
                                cursor = c_start
                                continue
                            if (c_start - cursor) < min_valid_attendance_minutes:
                                cursor = c_start
                                continue
                            extra_text = (
                                f"{cursor // 60:02d}:{cursor % 60:02d}\n"
                                f"{c_start // 60:02d}:{c_start % 60:02d}"
                            )
                            extra_slot = slot_index_for_block(extra_text)
                            if extra_slot is not None and extra_slot not in scheduled_slots:
                                _append_slot_value(
                                    slot_values,
                                    extra_slot,
                                    normalize_extra_block_text(
                                        extra_text,
                                        duplicate_window_minutes=duplicate_mark_window_minutes,
                                        extra_early_rounding_minutes=extra_early_rounding_minutes,
                                        extra_block_minutes=extra_block_minutes,
                                    ),
                                )
                        cursor = max(cursor, c_end)
                    if cursor < exit_min:
                        if (exit_min - cursor) < min_valid_attendance_minutes:
                            continue
                        extra_text = (
                            f"{cursor // 60:02d}:{cursor % 60:02d}\n"
                            f"{exit_min // 60:02d}:{exit_min % 60:02d}"
                        )
                        extra_slot = slot_index_for_block(extra_text)
                        if extra_slot is not None and extra_slot not in scheduled_slots:
                            _append_slot_value(
                                slot_values,
                                extra_slot,
                                normalize_extra_block_text(
                                    extra_text,
                                    duplicate_window_minutes=duplicate_mark_window_minutes,
                                    extra_early_rounding_minutes=extra_early_rounding_minutes,
                                    extra_block_minutes=extra_block_minutes,
                                ),
                            )
                    continue

                fallback_text = (
                    f"{entry_min // 60:02d}:{entry_min % 60:02d}\n"
                    f"{exit_min // 60:02d}:{exit_min % 60:02d}"
                )
                slot_idx = slot_index_for_block(fallback_text)
                display_text = fallback_text
                if slot_idx is None or slot_idx not in scheduled_slots:
                    display_text = normalize_extra_block_text(
                        fallback_text,
                        duplicate_window_minutes=duplicate_mark_window_minutes,
                        extra_early_rounding_minutes=extra_early_rounding_minutes,
                        extra_block_minutes=extra_block_minutes,
                    )
                    if slot_idx is None:
                        slot_idx = slot_index_for_block(display_text)
                if slot_idx is not None:
                    _append_slot_value(slot_values, slot_idx, display_text)

            if any_assigned:
                continue

            slot_idx = slot_index_for_block(block_text)
            display_text = block_text
            if slot_idx is None or slot_idx not in scheduled_slots:
                display_text = normalize_extra_block_text(
                    block_text,
                    duplicate_window_minutes=duplicate_mark_window_minutes,
                    extra_early_rounding_minutes=extra_early_rounding_minutes,
                    extra_block_minutes=extra_block_minutes,
                )
                if slot_idx is None:
                    slot_idx = slot_index_for_block(display_text)
            if slot_idx is not None:
                _append_slot_value(slot_values, slot_idx, display_text)
        result.append(slot_values)
    return result
