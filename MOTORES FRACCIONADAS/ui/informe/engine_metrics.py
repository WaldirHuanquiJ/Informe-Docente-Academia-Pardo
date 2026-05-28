from __future__ import annotations

import re

from app.models import TeacherRecord
from app.services.schedule_utils import TIME_SLOTS, scheduled_slots_for_teacher_weekday, slot_bounds_minutes, slot_duration_seconds
from app.services.time_rules import compute_seconds_from_mark_text, split_cell_blocks


def compute_teacher_metrics(view, teacher: TeacherRecord) -> dict:
    if not view.report:
        return {}
    base = view._report_column_metrics(teacher, view.report.days)
    total_seconds = base["total_asistencia"]
    tardiness_seconds = base["total_tardanza"]
    active_days = len([d for d in view.report.days if view._mark_for_day(teacher, d).strip()])

    absence_seconds = base["falta"]
    extra_seconds = base["horas_extra"]
    extra_tardy_seconds = base["tardanza_extra"]

    expected_seconds = 0
    for day in view.report.days:
        try:
            if view.report.period_start:
                weekday = view.report.period_start.replace(day=day).weekday()
            else:
                continue
        except ValueError:
            continue
        for s in scheduled_slots_for_teacher_weekday(
            teacher.teacher_id, teacher.name, teacher.department, view._slots_for_day(day), weekday
        ):
            expected_seconds += slot_duration_seconds(s)

    attendance_base = max(total_seconds + absence_seconds, 1)
    attendance_pct = min(int(round((total_seconds / attendance_base) * 100.0)), 100) if total_seconds > 0 else 0
    scheduled_blocks = 0
    if view.report and view.report.period_start:
        for day in view.report.days:
            try:
                weekday = view.report.period_start.replace(day=day).weekday()
            except ValueError:
                continue
            scheduled_blocks += len(
                scheduled_slots_for_teacher_weekday(
                    teacher.teacher_id,
                    teacher.name,
                    teacher.department,
                    view._slots_for_day(day),
                    weekday,
                )
            )
    absence_blocks = max(int(round(absence_seconds / 3600.0)), 0)
    pending_regularization = view._pending_regularization_count(teacher, view.report.days)
    fulfilled_blocks = max(scheduled_blocks - absence_blocks - pending_regularization, 0)
    compliance_pct = min(int(round((fulfilled_blocks / max(scheduled_blocks, 1)) * 100.0)), 100) if scheduled_blocks > 0 else 0

    return {
        "total_hours": total_seconds,
        "tardiness": tardiness_seconds,
        "absence": absence_seconds,
        "early_leave": base["salida_anticipada"],
        "extra": extra_seconds,
        "extra_tardy": extra_tardy_seconds,
        "extra_incomplete": base["extra_incompleta"],
        "expected": expected_seconds,
        "attendance_pct": attendance_pct,
        "active_days": active_days,
        "total_days": len(view.report.days),
        "scheduled_blocks": scheduled_blocks,
        "fulfilled_blocks": fulfilled_blocks,
        "pending_regularization": pending_regularization,
        "absence_blocks": absence_blocks,
        "schedule_compliance_pct": compliance_pct,
    }


def pending_regularization_count(view, teacher: TeacherRecord, days: list[int]) -> int:
    if not view.report:
        return 0
    day_slot_values = view._reporte_engine._build_day_slot_values(teacher)
    day_idx_map = {d: i for i, d in enumerate(view.report.days)}
    total = 0
    for day in days:
        pos = day_idx_map.get(day)
        if pos is None or pos >= len(day_slot_values):
            continue
        slots = day_slot_values[pos]
        scheduled = view._reporte_engine._scheduled_slots_for_teacher_day(teacher, day)
        for idx in scheduled:
            if not (0 <= idx < len(slots)):
                continue
            value = slots[idx]
            if value.strip() and view._is_pending_regularization_block(value):
                total += 1
    return total


def report_column_metrics(view, teacher: TeacherRecord, days: list[int]) -> dict[str, int]:
    day_slot_values = view._reporte_engine._build_day_slot_values(teacher)
    day_idx_map = {d: i for i, d in enumerate(view.report.days)} if view.report else {}

    total_asistencia = 0
    total_tardanza = 0
    salida_anticipada_min = 0
    horas_extra = 0
    tardanza_extra = 0
    extra_incompleta_min = 0

    for day in days:
        if day not in day_idx_map:
            continue
        day_pos = day_idx_map[day]
        slots = day_slot_values[day_pos] if day_pos < len(day_slot_values) else []
        scheduled_slots = view._reporte_engine._scheduled_slots_for_teacher_day(teacher, day)

        for idx, value in enumerate(slots):
            if not value.strip():
                continue
            if idx in scheduled_slots:
                eff = view._reporte_engine._effective_block_seconds(value, idx)
                if eff >= view._reporte_engine.MIN_VALID_ATTENDANCE_MINUTES * 60:
                    total_asistencia += eff
                    total_tardanza += view._reporte_engine._compute_scheduled_tardiness_seconds(
                        teacher, day, idx, value
                    )
                    salida_anticipada_min += view._reporte_engine._early_departure_minutes_for_block(value, idx)
            else:
                total_asistencia += compute_seconds_from_mark_text(value)
                ex_s, ex_t = view._reporte_engine._extra_block_metrics(value)
                if ex_s >= view._reporte_engine.MIN_VALID_ATTENDANCE_MINUTES * 60:
                    horas_extra += ex_s
                    tardanza_extra += ex_t
                    extra_incompleta_min += view._reporte_engine._extra_early_departure_minutes_for_block(value)

    salida_anticipada = salida_anticipada_min * 60
    extra_incompleta = extra_incompleta_min * 60
    horas_extra_neta = max(horas_extra - tardanza_extra - extra_incompleta, 0)
    falta = view._reporte_engine._count_teacher_faltas(teacher, set(days)) * 3600
    return {
        "total_asistencia": total_asistencia,
        "total_tardanza": total_tardanza,
        "salida_anticipada": salida_anticipada,
        "horas_extra": horas_extra,
        "horas_extra_neta": horas_extra_neta,
        "tardanza_extra": tardanza_extra,
        "extra_incompleta": extra_incompleta,
        "falta": falta,
    }


def is_pending_regularization_block(view, block_text: str) -> bool:
    if "PENDIENTE" in (block_text or "").upper():
        return True
    return len(view._normalized_event_minutes(block_text)) % 2 == 1


def day_total_seconds(view, teacher: TeacherRecord, day: int) -> int:
    slot_matrix = view._build_day_slot_values(teacher)
    if not view.report:
        return 0
    try:
        day_idx = view.report.days.index(day)
    except ValueError:
        return 0
    if not (0 <= day_idx < len(slot_matrix)):
        return 0
    day_slots = slot_matrix[day_idx]
    scheduled_slots = set()
    if view.report.period_start:
        try:
            weekday = view.report.period_start.replace(day=day).weekday()
            scheduled_slots = scheduled_slots_for_teacher_weekday(
                teacher.teacher_id,
                teacher.name,
                teacher.department,
                view._slots_for_day(day),
                weekday,
            )
        except ValueError:
            scheduled_slots = set()
    total = 0
    for idx, value in enumerate(day_slots):
        if not value.strip():
            continue
        if idx in scheduled_slots:
            total += view._effective_block_seconds(value, idx)
        else:
            extra_block_seconds, _extra_tardy = view._extra_block_metrics(value)
            if extra_block_seconds >= view.MIN_VALID_ATTENDANCE_SECONDS:
                total += extra_block_seconds
    return total
