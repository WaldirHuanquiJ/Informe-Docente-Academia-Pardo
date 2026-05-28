from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from app.models import TeacherRecord
from app.services.schedule_utils import TIME_SLOTS, SLOT_START_MINUTES, format_hm, scheduled_slots_for_teacher_weekday, slot_bounds_minutes, slot_duration_seconds

def fill_daily_table(view, teacher: TeacherRecord) -> None:
        if not view.report:
            return
        view.daily_table.setUpdatesEnabled(False)
        view.daily_table.blockSignals(True)
        weekday_names = {0: "LUN", 1: "MAR", 2: "MIE", 3: "JUE", 4: "VIE", 5: "SAB", 6: "DOM"}
        headers = [
            "Dia", "Sem.", "Entrada", "Salida", "Horas", "Tardanza", "Estado",
            "Salida Ant.", "Extra", "Extra Incomp.", "En horario", "Fuera horario",
        ]
        data: list[list] = []
        day_order = sorted(view.report.days)
        slot_matrix = view._build_day_slot_values(teacher)
        slots_by_day = {day: slot_matrix[idx] for idx, day in enumerate(view.report.days)}

        for day in day_order:
            slot_values = slots_by_day.get(day, [])
            raw_mark = (view._mark_for_day(teacher, day) or "").strip()
            day_seconds = 0
            is_sunday = False
            scheduled_slots = set()
            if view.report.period_start:
                try:
                    weekday = view.report.period_start.replace(day=day).weekday()
                    is_sunday = weekday == 6
                    scheduled_slots = scheduled_slots_for_teacher_weekday(
                        teacher.teacher_id, teacher.name, teacher.department,
                        view._slots_for_day(day), weekday,
                    )
                except ValueError:
                    scheduled_slots = set()
                    is_sunday = False
            if is_sunday:
                # Regla de negocio: domingos se consideran horas extra.
                scheduled_slots = set()

            def _scheduled_intervals_with_grace() -> list[tuple[int, int]]:
                intervals: list[tuple[int, int]] = []
                for sidx in sorted(scheduled_slots):
                    bounds = slot_bounds_minutes(sidx)
                    if bounds is None:
                        continue
                    start, end = bounds
                    intervals.append((start - view.OUT_OF_SCHEDULE_GRACE_MINUTES, end + view.OUT_OF_SCHEDULE_GRACE_MINUTES))
                return intervals

            def _outside_minutes(entry_min: int, exit_min: int) -> int:
                if exit_min <= entry_min:
                    return 0
                intervals = _scheduled_intervals_with_grace()
                if not intervals:
                    return max(exit_min - entry_min, 0)
                remaining: list[tuple[int, int]] = [(entry_min, exit_min)]
                for cover_start, cover_end in intervals:
                    new_remaining: list[tuple[int, int]] = []
                    for seg_start, seg_end in remaining:
                        if cover_end <= seg_start or cover_start >= seg_end:
                            new_remaining.append((seg_start, seg_end))
                            continue
                        if seg_start < cover_start:
                            new_remaining.append((seg_start, cover_start))
                        if cover_end < seg_end:
                            new_remaining.append((cover_end, seg_end))
                    remaining = new_remaining
                    if not remaining:
                        break
                return sum(max(seg_end - seg_start, 0) for seg_start, seg_end in remaining)

            for idx in range(len(TIME_SLOTS)):
                if idx in scheduled_slots:
                    day_seconds += view._effective_block_seconds(slot_values[idx], idx)
                else:
                    extra_block_seconds, _extra_tardy = view._extra_block_metrics(slot_values[idx])
                    if extra_block_seconds >= view.MIN_VALID_ATTENDANCE_SECONDS:
                        day_seconds += extra_block_seconds

            tardy_seconds = view._teacher_scheduled_tardiness_seconds(teacher, [day])
            tardy_min = tardy_seconds // 60
            early_leave_minutes = 0
            extra_incomplete_minutes = 0
            extra_seconds_day = 0
            for idx in scheduled_slots:
                value = slot_values[idx] if 0 <= idx < len(slot_values) else ""
                if not value.strip() or view._is_pending_regularization_block(value):
                    continue
                early_leave_minutes += view._early_departure_minutes_for_block(value, idx)
            for idx, value in enumerate(slot_values):
                if idx in scheduled_slots or not value.strip() or view._is_pending_regularization_block(value):
                    continue
                extra_incomplete_minutes += view._extra_early_departure_minutes_for_block(value)
                extra_block_seconds, _extra_tardy = view._extra_block_metrics(value)
                if extra_block_seconds >= view.MIN_VALID_ATTENDANCE_SECONDS:
                    extra_seconds_day += extra_block_seconds

            # Entradas/salidas por turno (linea por turno), etiquetado T1, T2...
            # Construido por slots contiguos para evitar colapsos de T2/T3 por normalizacion.
            slot_segments: list[tuple[int, int, int]] = []
            for idx, value in enumerate(slot_values):
                if not (value or "").strip():
                    continue
                # Importante: usar TODOS los pares del slot para no colapsar T2/T3.
                for entry_min, exit_min in view._extract_entry_exit_pairs(value):
                    if exit_min <= entry_min:
                        continue
                    slot_segments.append((idx, entry_min, exit_min))

            slot_segments.sort(key=lambda x: x[0])
            merged_turn_rows: list[tuple[int, int]] = []
            current_start: int | None = None
            current_end: int | None = None
            prev_slot: int | None = None
            for slot_idx, seg_start, seg_end in slot_segments:
                if current_start is None:
                    current_start, current_end, prev_slot = seg_start, seg_end, slot_idx
                    continue
                is_contiguous_slot = (prev_slot is not None and slot_idx <= prev_slot + 1)
                is_time_continuous = current_end is not None and seg_start <= (current_end + 20)
                if is_contiguous_slot and is_time_continuous:
                    current_end = max(current_end or seg_end, seg_end)
                    prev_slot = slot_idx
                    continue
                merged_turn_rows.append((current_start, current_end or current_start))
                current_start, current_end, prev_slot = seg_start, seg_end, slot_idx
            if current_start is not None:
                merged_turn_rows.append((current_start, current_end or current_start))

            # Turnos base por horario programado del dia (garantiza T2/T3 aunque marcas vengan compactas).
            scheduled_groups: list[list[int]] = []
            for slot_idx in sorted(scheduled_slots):
                if not scheduled_groups or slot_idx != scheduled_groups[-1][-1] + 1:
                    scheduled_groups.append([slot_idx])
                else:
                    scheduled_groups[-1].append(slot_idx)

            turn_rows: list[tuple[int, int]] = []
            if scheduled_groups:
                # Asignar por grupo de slots: entrada minima y salida maxima dentro del grupo.
                for group in scheduled_groups:
                    g_start: int | None = None
                    g_end: int | None = None
                    for slot_idx in group:
                        if not (0 <= slot_idx < len(slot_values)):
                            continue
                        value = slot_values[slot_idx]
                        if not (value or "").strip():
                            continue
                        for entry_min, exit_min in view._extract_entry_exit_pairs(value):
                            if exit_min <= entry_min:
                                continue
                            g_start = entry_min if g_start is None else min(g_start, entry_min)
                            g_end = exit_min if g_end is None else max(g_end, exit_min)
                    if g_start is not None and g_end is not None:
                        turn_rows.append((g_start, g_end))
                    else:
                        # Sin marca en ese turno programado: mostrar el turno esperado del horario.
                        bounds_start = slot_bounds_minutes(group[0])
                        bounds_end = slot_bounds_minutes(group[-1])
                        if bounds_start and bounds_end:
                            turn_rows.append((bounds_start[0], bounds_end[1]))
            else:
                # Sin horario detectado: usar segmentos por marcas.
                turn_rows = list(merged_turn_rows)

            turn_lines = [
                (
                    f"T{i + 1}",
                    f"{start // 60:02d}:{start % 60:02d}",
                    f"{end // 60:02d}:{end % 60:02d}",
                )
                for i, (start, end) in enumerate(turn_rows)
            ]

            per_turn_rows: list[dict[str, str]] = []
            if scheduled_groups:
                for i, group in enumerate(scheduled_groups):
                    tlabel = f"T{i + 1}"
                    g_start_bounds = slot_bounds_minutes(group[0])
                    g_end_bounds = slot_bounds_minutes(group[-1])
                    if not g_start_bounds or not g_end_bounds:
                        continue
                    g_entry = ""
                    g_exit = ""
                    g_seconds = 0
                    g_tardy = 0
                    g_early = 0
                    g_faltas = 0
                    g_pending = 0
                    has_any = False
                    for slot_idx in group:
                        value = slot_values[slot_idx] if 0 <= slot_idx < len(slot_values) else ""
                        if not value.strip():
                            g_faltas += 1
                            continue
                        has_any = True
                        if view._is_pending_regularization_block(value):
                            g_pending += 1
                            continue
                        eff = view._effective_block_seconds(value, slot_idx)
                        if eff < view.MIN_VALID_ATTENDANCE_SECONDS:
                            g_faltas += 1
                        g_seconds += eff
                        times = re.findall(r"([01]?\d|2[0-3]):([0-5]\d)", value)
                        if times:
                            try:
                                e_min = int(times[0][0]) * 60 + int(times[0][1])
                                x_min = int(times[-1][0]) * 60 + int(times[-1][1])
                                if not g_entry or e_min < int(g_entry[:2]) * 60 + int(g_entry[3:5]):
                                    g_entry = f"{e_min // 60:02d}:{e_min % 60:02d}"
                                if not g_exit or x_min > int(g_exit[:2]) * 60 + int(g_exit[3:5]):
                                    g_exit = f"{x_min // 60:02d}:{x_min % 60:02d}"
                            except Exception:
                                pass
                        if times and not view._is_pending_regularization_block(value) and eff >= view.MIN_VALID_ATTENDANCE_SECONDS:
                            slot_tardy = max((int(times[0][0]) * 60 + int(times[0][1])) - SLOT_START_MINUTES[slot_idx], 0) * 60
                            slot_cap = slot_duration_seconds(slot_idx)
                            if slot_cap > 0:
                                slot_tardy = min(slot_tardy, slot_cap)
                            g_tardy += slot_tardy
                        g_early += view._early_departure_minutes_for_block(value, slot_idx)

                    if not g_entry:
                        g_entry = f"{g_start_bounds[0] // 60:02d}:{g_start_bounds[0] % 60:02d}"
                    if not g_exit:
                        g_exit = f"{g_end_bounds[1] // 60:02d}:{g_end_bounds[1] % 60:02d}"

                    if not has_any:
                        g_estado = "FALTA"
                    elif g_pending > 0:
                        g_estado = "PENDIENTE"
                    elif g_faltas > 0:
                        g_estado = "FALTA"
                    elif g_tardy > 0:
                        g_estado = f"TARDE ({g_tardy // 60}m)"
                    else:
                        g_estado = "PUNTUAL"

                    g_turno = f"{g_start_bounds[0] // 60:02d}:{g_start_bounds[0] % 60:02d}-{g_end_bounds[1] // 60:02d}:{g_end_bounds[1] % 60:02d}"
                    per_turn_rows.append(
                        {
                            "label": tlabel,
                            "entry": g_entry,
                            "exit": g_exit,
                            "hours": f"{g_seconds / 3600:.1f}h",
                            "tardy": f"{g_tardy // 60}m",
                            "estado": g_estado,
                            "salida_ant": format_hm(g_early * 60),
                            "extra": "00:00",
                            "extra_inc": "00:00",
                            "in_h": g_turno,
                            "out_h": "",
                        }
                    )
                # Agregar subfilas de horas extra fuera de horario (X1, X2, ...)
                extra_idx = 1
                for slot_idx, value in enumerate(slot_values):
                    if slot_idx in scheduled_slots:
                        continue
                    if not (value or "").strip() or view._is_pending_regularization_block(value):
                        continue
                    for entry_min, exit_min in view._extract_entry_exit_pairs(value):
                        if exit_min <= entry_min:
                            continue
                        outside_min = _outside_minutes(entry_min, exit_min)
                        if outside_min < view.OUT_OF_SCHEDULE_MIN_BLOCK_MINUTES:
                            continue
                        extra_text = (
                            f"{entry_min // 60:02d}:{entry_min % 60:02d}\n"
                            f"{exit_min // 60:02d}:{exit_min % 60:02d}"
                        )
                        ex_seconds, ex_tardy = view._extra_block_metrics(extra_text)
                        if ex_seconds < view.MIN_VALID_ATTENDANCE_SECONDS:
                            continue
                        ex_in_h = "-"
                        ex_out_h = f"{entry_min // 60:02d}:{entry_min % 60:02d}-{exit_min // 60:02d}:{exit_min % 60:02d}"
                        per_turn_rows.append(
                            {
                                "label": f"X{extra_idx}",
                                "entry": f"{entry_min // 60:02d}:{entry_min % 60:02d}",
                                "exit": f"{exit_min // 60:02d}:{exit_min % 60:02d}",
                                "hours": f"{ex_seconds / 3600:.1f}h",
                                "tardy": f"{ex_tardy // 60}m",
                                "estado": "EXTRA",
                                "salida_ant": "00:00",
                                "extra": format_hm(ex_seconds),
                                "extra_inc": format_hm(view._extra_early_departure_minutes_for_block(extra_text) * 60),
                                "in_h": ex_in_h,
                                "out_h": ex_out_h,
                            }
                        )
                        extra_idx += 1
            else:
                # Sin grupos programados: mostrar solo bloques extra reales (evita falsos positivos).
                extra_idx = 1
                for slot_idx, value in enumerate(slot_values):
                    if not (value or "").strip() or view._is_pending_regularization_block(value):
                        continue
                    for entry_min, exit_min in view._extract_entry_exit_pairs(value):
                        if exit_min <= entry_min:
                            continue
                        outside_min = _outside_minutes(entry_min, exit_min)
                        if outside_min < view.OUT_OF_SCHEDULE_MIN_BLOCK_MINUTES:
                            continue
                        ex_text = (
                            f"{entry_min // 60:02d}:{entry_min % 60:02d}\n"
                            f"{exit_min // 60:02d}:{exit_min % 60:02d}"
                        )
                        ex_seconds, ex_tardy = view._extra_block_metrics(ex_text)
                        if ex_seconds < view.MIN_VALID_ATTENDANCE_SECONDS:
                            continue
                        per_turn_rows.append(
                            {
                                "label": f"X{extra_idx}",
                                "entry": f"{entry_min // 60:02d}:{entry_min % 60:02d}",
                                "exit": f"{exit_min // 60:02d}:{exit_min % 60:02d}",
                                "hours": f"{ex_seconds / 3600:.1f}h",
                                "tardy": f"{ex_tardy // 60}m",
                                "estado": "EXTRA",
                                "salida_ant": "00:00",
                                "extra": format_hm(ex_seconds),
                                "extra_inc": format_hm(view._extra_early_departure_minutes_for_block(ex_text) * 60),
                                "in_h": "-",
                                "out_h": f"{entry_min // 60:02d}:{entry_min % 60:02d}-{exit_min // 60:02d}:{exit_min % 60:02d}",
                            }
                        )
                        extra_idx += 1

            try:
                wday = weekday_names.get(view.report.period_start.replace(day=day).weekday(), "") if view.report.period_start else ""
            except ValueError:
                wday = ""

            marked_slots = set()
            for idx, value in enumerate(slot_values):
                if not value.strip():
                    continue
                if view._is_pending_regularization_block(value):
                    continue
                if idx in scheduled_slots:
                    marked_slots.add(idx)
                    continue
                has_valid_outside = False
                for entry_min, exit_min in view._extract_entry_exit_pairs(value):
                    outside_min = _outside_minutes(entry_min, exit_min)
                    if outside_min >= view.OUT_OF_SCHEDULE_MIN_BLOCK_MINUTES:
                        has_valid_outside = True
                        break
                if has_valid_outside:
                    marked_slots.add(idx)

            in_schedule_slots = sorted(marked_slots.intersection(scheduled_slots))
            out_schedule_slots = sorted(marked_slots.difference(scheduled_slots))
            in_schedule_text = view._compact_slot_labels(in_schedule_slots) if in_schedule_slots else "-"
            out_schedule_text = view._compact_slot_labels(out_schedule_slots) if out_schedule_slots else "-"
            turnos_lines: list[str] = []
            if in_schedule_slots:
                turnos_lines.append(f"H: {in_schedule_text}")
            if out_schedule_slots:
                turnos_lines.append(f"X: {out_schedule_text}")
            turnos_text = "\n".join(turnos_lines) if turnos_lines else "-"

            # Base real del biometrico para el dia (evita perder estado por mapeo de slots).
            any_mark = bool(raw_mark)
            scheduled_faltas = 0
            scheduled_pendientes = 0
            for idx in scheduled_slots:
                value = slot_values[idx] if 0 <= idx < len(slot_values) else ""
                if not value.strip():
                    scheduled_faltas += 1
                    continue
                if view._is_pending_regularization_block(value):
                    scheduled_pendientes += 1
                    continue
                if view._effective_block_seconds(value, idx) < view.MIN_VALID_ATTENDANCE_SECONDS:
                    scheduled_faltas += 1

            if not any_mark:
                estado = "FALTA" if scheduled_slots else "SIN REGISTRO"
            elif scheduled_slots and scheduled_pendientes > 0:
                estado = "PENDIENTE"
            elif scheduled_slots and scheduled_faltas > 0:
                estado = "FALTA"
            elif is_sunday and (extra_seconds_day > 0):
                estado = "EXTRA"
            elif tardy_min > 0:
                estado = f"TARDE ({tardy_min}m)"
            else:
                estado = "PUNTUAL"

            if not per_turn_rows:
                data.append([
                    str(day), wday, "", "", f"{day_seconds / 3600:.1f}h", f"{tardy_min}m", estado,
                    format_hm(early_leave_minutes * 60),
                    format_hm(extra_seconds_day),
                    format_hm(extra_incomplete_minutes * 60),
                    in_schedule_text, out_schedule_text,
                ])
            else:
                for turn_idx, row_turn in enumerate(per_turn_rows):
                    is_first = turn_idx == 0
                    data.append([
                        str(day),
                        wday,
                        f"{row_turn['label']} {row_turn['entry']}",
                        f"{row_turn['label']} {row_turn['exit']}",
                        row_turn["hours"] if row_turn["hours"] else (f"{day_seconds / 3600:.1f}h" if is_first else ""),
                        row_turn["tardy"] if row_turn["tardy"] else (f"{tardy_min}m" if is_first else ""),
                        row_turn["estado"] if row_turn["estado"] else (estado if is_first else ""),
                        row_turn["salida_ant"] if row_turn["salida_ant"] else (format_hm(early_leave_minutes * 60) if is_first else ""),
                        row_turn["extra"] if row_turn.get("extra") else (format_hm(extra_seconds_day) if is_first else ""),
                        row_turn["extra_inc"] if row_turn["extra_inc"] else (format_hm(extra_incomplete_minutes * 60) if is_first else ""),
                        row_turn["in_h"] if row_turn["in_h"] else (in_schedule_text if is_first else ""),
                        row_turn["out_h"],
                    ])

        def _parse_duration_seconds(text: str) -> int:
            raw = (text or "").strip().lower()
            if not raw:
                return 0
            m_hhmm = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
            if m_hhmm:
                return int(m_hhmm.group(1)) * 3600 + int(m_hhmm.group(2)) * 60
            m_h = re.fullmatch(r"(\d+(?:\.\d+)?)h", raw.replace(" ", ""))
            if m_h:
                return int(round(float(m_h.group(1)) * 3600))
            m_m = re.fullmatch(r"(\d+)m", raw.replace(" ", ""))
            if m_m:
                return int(m_m.group(1)) * 60
            return 0

        # Fila total de auditoria al final de la tabla.
        total_hours = 0
        total_tardy = 0
        total_early = 0
        total_extra = 0
        total_extra_inc = 0
        for row in data:
            total_hours += _parse_duration_seconds(row[4] if len(row) > 4 else "")
            total_tardy += _parse_duration_seconds(row[5] if len(row) > 5 else "")
            total_early += _parse_duration_seconds(row[7] if len(row) > 7 else "")
            total_extra += _parse_duration_seconds(row[8] if len(row) > 8 else "")
            total_extra_inc += _parse_duration_seconds(row[9] if len(row) > 9 else "")
        data.append([
            "TOTAL", "", "", "",
            f"{total_hours / 3600:.1f}h",
            f"{total_tardy // 60}m",
            "",
            format_hm(total_early),
            format_hm(total_extra),
            format_hm(total_extra_inc),
            "", "",
        ])

        view.daily_table.setRowCount(len(data))
        view.daily_table.setColumnCount(12)
        view.daily_table.setHorizontalHeaderLabels(headers)
        for i, row in enumerate(data):
            for j, val in enumerate(row):
                item = QTableWidgetItem(val)
                if j in (2, 3):  # Entrada, Salida
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                view.daily_table.setItem(i, j, item)
        view.daily_table.setWordWrap(True)
        view.daily_table.resizeRowsToContents()
        view.daily_table.resizeColumnsToContents()
        view.daily_table.blockSignals(False)
        view.daily_table.setUpdatesEnabled(True)


def fill_weekly_table(view, teacher: TeacherRecord, metrics: dict) -> None:
        if not view.report:
            return
        view.weekly_table.setUpdatesEnabled(False)
        view.weekly_table.blockSignals(True)

        sorted_days = sorted(view.report.days)
        weeks: list[list[int]] = []
        curr: list[int] = []
        week_idx = 1
        for day in sorted_days:
            if view.report.period_start:
                try:
                    if view.report.period_start.replace(day=day).weekday() == 6 and curr:
                        weeks.append(curr)
                        curr = []
                except ValueError:
                    pass
            curr.append(day)
        if curr:
            weeks.append(curr)

        slot_matrix = view._build_day_slot_values(teacher)
        slots_by_day = {day: slot_matrix[idx] for idx, day in enumerate(view.report.days)}
        day_to_seconds: dict[int, int] = {}
        for day_pos, day in enumerate(sorted_days):
            mark = "\n".join(v for v in slots_by_day.get(day, []) if v.strip())
            slot_values = slots_by_day.get(day, [""] * len(TIME_SLOTS))
            scheduled_slots = set()
            if view.report.period_start:
                try:
                    weekday = view.report.period_start.replace(day=day).weekday()
                    scheduled_slots = scheduled_slots_for_teacher_weekday(
                        teacher.teacher_id, teacher.name, teacher.department,
                        view._slots_for_day(day), weekday,
                    )
                except ValueError:
                    scheduled_slots = set()
            total_day = 0
            for idx in range(len(TIME_SLOTS)):
                if idx in scheduled_slots:
                    total_day += view._effective_block_seconds(slot_values[idx], idx)
                else:
                    extra_block_seconds, _extra_tardy = view._extra_block_metrics(slot_values[idx])
                    if extra_block_seconds >= view.MIN_VALID_ATTENDANCE_SECONDS:
                        total_day += extra_block_seconds
            day_to_seconds[day] = total_day

        headers = ["Semana", "Días", "Horas", "Tardanza", "Rendimiento"]
        data: list[list] = []
        for w_days in weeks:
            total_s = sum(day_to_seconds.get(d, 0) for d in w_days)
            tardy_s = view._teacher_scheduled_tardiness_seconds(teacher, w_days)
            exp = 0
            if view.report and view.report.period_start:
                for d in w_days:
                    try:
                        weekday = view.report.period_start.replace(day=d).weekday()
                    except ValueError:
                        continue
                    for s in scheduled_slots_for_teacher_weekday(
                        teacher.teacher_id, teacher.name, teacher.department,
                        view._slots_for_day(d), weekday,
                    ):
                        exp += slot_duration_seconds(s)
            perf = min(int((total_s / max(exp, 1)) * 100), 100)

            data.append([
                f"Semana {week_idx}",
                f"{min(w_days)}–{max(w_days)} ({len(w_days)}d)",
                format_hm(total_s),
                format_hm(tardy_s),
                f"{perf}%",
            ])
            week_idx += 1

        view.weekly_table.setRowCount(len(data))
        view.weekly_table.setColumnCount(5)
        view.weekly_table.setHorizontalHeaderLabels(headers)
        for i, row in enumerate(data):
            for j, val in enumerate(row):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                view.weekly_table.setItem(i, j, item)
        view.weekly_table.resizeColumnsToContents()
        view.weekly_table.blockSignals(False)
        view.weekly_table.setUpdatesEnabled(True)

