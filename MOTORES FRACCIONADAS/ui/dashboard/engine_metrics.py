from __future__ import annotations

from app.models import TeacherRecord
from app.services.schedule_utils import TIME_SLOTS, SLOT_START_MINUTES, scheduled_slots_for_teacher_weekday, slot_bounds_minutes, slot_duration_seconds
from app.services.time_rules import compute_seconds_from_mark_text


def day_total_seconds(view, teacher: TeacherRecord, day: int) -> int:
    slots = view._build_day_slot_values(teacher, day)
    scheduled_slots = set()
    if view.report and view.report.period_start:
        try:
            weekday = view.report.period_start.replace(day=day).weekday()
            scheduled_slots = scheduled_slots_for_teacher_weekday(
                teacher.teacher_id, teacher.name, teacher.department, view._slots_for_day(day), weekday
            )
        except ValueError:
            scheduled_slots = set()
    total = 0
    for idx, value in enumerate(slots):
        if not value.strip():
            continue
        if idx in scheduled_slots:
            total += view._effective_block_seconds(value, idx)
        else:
            total += compute_seconds_from_mark_text(value)
    return total


def effective_block_seconds(view, block_text: str, slot_idx: int) -> int:
    return view._reporte_engine._effective_block_seconds(block_text, slot_idx)


def teacher_absence_seconds(view, teacher: TeacherRecord, days: list[int]) -> int:
    if not view.report or not view.report.period_start:
        return 0
    total = 0
    for day in days:
        slots = view._build_day_slot_values(teacher, day)
        try:
            weekday = view.report.period_start.replace(day=day).weekday()
        except ValueError:
            continue
        scheduled = scheduled_slots_for_teacher_weekday(
            teacher.teacher_id, teacher.name, teacher.department, view._slots_for_day(day), weekday
        )
        for idx in scheduled:
            val = slots[idx] if 0 <= idx < len(slots) else ""
            if not val.strip() or view._is_pending_regularization_block(val) or view._effective_block_seconds(val, idx) < view.MIN_VALID_ATTENDANCE_SECONDS:
                dur = slot_duration_seconds(idx)
                total += dur if dur > 0 else view.MIN_VALID_ATTENDANCE_SECONDS
    return total


def is_pending_regularization_block(view, block_text: str) -> bool:
    return view._reporte_engine._is_pending_regularization_block(block_text)


def teacher_extra_metrics(view, teacher: TeacherRecord, days: list[int]) -> tuple[int, int]:
    total_extra = 0
    total_extra_tardy = 0
    for day in days:
        slots = view._build_day_slot_values(teacher, day)
        scheduled = view._reporte_engine._scheduled_slots_for_teacher_day(teacher, day)
        for idx, value in enumerate(slots):
            if idx in scheduled or not value.strip():
                continue
            ex_s, ex_t = view._extra_block_metrics(value)
            if ex_s >= view.MIN_VALID_ATTENDANCE_SECONDS:
                total_extra += ex_s
                total_extra_tardy += ex_t
    return total_extra, total_extra_tardy


def report_column_metrics(view, teacher: TeacherRecord, days: list[int]) -> dict[str, int]:
    total_asistencia = 0
    total_tardanza = 0
    salida_anticipada = 0
    horas_extra = 0
    tardanza_extra = 0
    extra_incompleta = 0

    for day in days:
        slots = view._build_day_slot_values(teacher, day)
        scheduled = view._reporte_engine._scheduled_slots_for_teacher_day(teacher, day)
        for idx, value in enumerate(slots):
            if not value.strip():
                continue
            if idx in scheduled:
                eff = view._reporte_engine._effective_block_seconds(value, idx)
                if eff >= view._reporte_engine.MIN_VALID_ATTENDANCE_MINUTES * 60:
                    total_asistencia += eff
                    total_tardanza += view._reporte_engine._compute_scheduled_tardiness_seconds(teacher, day, idx, value)
                    salida_anticipada += view._reporte_engine._early_departure_minutes_for_block(value, idx) * 60
            else:
                total_asistencia += compute_seconds_from_mark_text(value)
                ex_s, ex_t = view._reporte_engine._extra_block_metrics(value)
                if ex_s >= view._reporte_engine.MIN_VALID_ATTENDANCE_MINUTES * 60:
                    horas_extra += ex_s
                    tardanza_extra += ex_t
                    extra_incompleta += view._reporte_engine._extra_early_departure_minutes_for_block(value) * 60

    faltas = view._reporte_engine._count_teacher_faltas(teacher, set(days)) * 3600
    horas_extra_neta = max(horas_extra - tardanza_extra - extra_incompleta, 0)
    return {
        "total_asistencia": total_asistencia,
        "total_tardanza": total_tardanza,
        "salida_anticipada": salida_anticipada,
        "horas_extra": horas_extra,
        "horas_extra_neta": horas_extra_neta,
        "tardanza_extra": tardanza_extra,
        "extra_incompleta": extra_incompleta,
        "falta": faltas,
    }
