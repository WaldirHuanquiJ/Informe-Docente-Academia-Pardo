from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import plotly.graph_objects as go
from plotly.io import to_html
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from app.models import AttendanceReport, TeacherRecord
from app.services.schedule_utils import slot_duration_seconds
from app.ui.reporte import ReporteView


def _format_hm(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    minutes = seconds // 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class ResumenView:
    """Vista analitica 100% apilada: asistencia vs deuda por horario/curso/docente."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._schedule_path = data_dir / "HORARIOS.xlsx"
        self._engine = ReporteView(data_dir)
        self._chart_html_path = data_dir / "_resumen_plotly.html"
        self.report: AttendanceReport | None = None
        self._theme_mode = "dark"
        self._rows_cache: list[dict[str, object]] = []

        self.tab = QWidget()
        self.tab.setObjectName("ResumenTab")

        self.title = QLabel("Resumen de Distribucion Horaria")
        self.title.setObjectName("ResumenTitle")
        self.subtitle = QLabel("Barras 100% apiladas: asistencia efectiva vs horas deuda por horario, curso o docente")
        self.subtitle.setObjectName("ResumenSubtitle")

        self.group_combo = QComboBox()
        self.group_combo.addItems(["Por horario", "Por curso", "Por docente"])
        self.group_combo.setObjectName("ResumenField")

        self.schedule_combo = QComboBox()
        self.schedule_combo.setObjectName("ResumenField")
        self.course_combo = QComboBox()
        self.course_combo.setObjectName("ResumenField")
        self.teacher_combo = QComboBox()
        self.teacher_combo.setObjectName("ResumenField")

        self.chart = QWebEngineView()
        self.chart.setMinimumHeight(420)
        self.chart.setObjectName("ResumenChart")

        self.table = QTableWidget()
        self.table.setObjectName("ResumenTable")
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["Grupo", "Docentes", "Cursos", "Asistencia", "Deuda", "Asignadas", "% Asistencia", "% Deuda"]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 8):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addWidget(QLabel("Agrupar:"))
        controls.addWidget(self.group_combo)
        controls.addWidget(QLabel("Horario:"))
        controls.addWidget(self.schedule_combo)
        controls.addWidget(QLabel("Curso:"))
        controls.addWidget(self.course_combo)
        controls.addWidget(QLabel("Docente:"))
        controls.addWidget(self.teacher_combo)
        controls.addStretch(1)

        header = QFrame()
        header.setObjectName("ResumenHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.addLayout(controls)

        layout = QVBoxLayout(self.tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addWidget(self.chart, 1)
        self.table.hide()

        self.group_combo.currentIndexChanged.connect(self._refresh_view)
        self.schedule_combo.currentIndexChanged.connect(self._refresh_view)
        self.course_combo.currentIndexChanged.connect(self._refresh_view)
        self.teacher_combo.currentIndexChanged.connect(self._refresh_view)

        self._apply_local_style()
        self._set_empty("Cargue un reporte y un horario para ver el resumen.")

    def set_theme_mode(self, theme_mode: str) -> None:
        self._theme_mode = "light" if theme_mode == "light" else "dark"
        self._apply_local_style()
        self._refresh_view()

    def set_schedule_file(self, schedule_path: Path) -> None:
        self._schedule_path = schedule_path
        self._engine.set_schedule_file(schedule_path)
        if self.report:
            self.refresh(self.report)

    def reload_schedule_source(self) -> None:
        self._engine.set_schedule_file(self._schedule_path)
        if self.report:
            self.refresh(self.report)

    def refresh(self, report: AttendanceReport) -> None:
        self.report = report
        self._engine.set_schedule_file(self._schedule_path)
        self._engine.set_report(report)
        self._rebuild_filter_options()
        self._refresh_view()

    def clear_all(self) -> None:
        self.report = None
        self.table.setRowCount(0)
        self._set_empty("Sin datos para resumir.")

    def _rebuild_filter_options(self) -> None:
        if not self.report:
            return
        schedules: set[str] = set()
        courses: set[str] = set()
        teachers: list[TeacherRecord] = []
        for teacher in self.report.teachers:
            courses.add((teacher.department or "Sin curso").strip() or "Sin curso")
            teachers.append(teacher)
            for day in self.report.days:
                for schedule_name, slots in self._engine._modality_slots_for_teacher_day(teacher, day).items():
                    if slots:
                        schedules.add(schedule_name)

        self._reset_combo(self.schedule_combo, ["Todos"] + sorted(schedules, key=str.lower))
        self._reset_combo(self.course_combo, ["Todos"] + sorted(courses, key=str.lower))
        teacher_items = ["Todos"] + [
            f"{t.name} ({t.teacher_id})" if t.teacher_id else t.name
            for t in sorted(teachers, key=lambda x: x.name.lower())
        ]
        self._reset_combo(self.teacher_combo, teacher_items)

    def _reset_combo(self, combo: QComboBox, values: list[str]) -> None:
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        idx = combo.findText(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _selected_teacher_name(self) -> str:
        text = self.teacher_combo.currentText().strip()
        if text == "Todos":
            return ""
        return text.rsplit(" (", 1)[0].strip()

    def _refresh_view(self) -> None:
        if not self.report:
            self._set_empty("Cargue un reporte y un horario para ver el resumen.")
            return
        rows = self._build_summary_rows()
        self._rows_cache = rows
        self._render_table(rows)
        self._render_chart(rows)

    def _build_summary_rows(self) -> list[dict[str, object]]:
        if not self.report:
            return []
        group_mode = self.group_combo.currentText()
        schedule_filter = self.schedule_combo.currentText().strip()
        course_filter = self.course_combo.currentText().strip()
        teacher_filter = self._selected_teacher_name()

        buckets: dict[str, dict[str, object]] = defaultdict(
            lambda: {"attendance": 0, "debt": 0, "assigned": 0, "teachers": set(), "courses": set()}
        )

        day_slot_values_by_teacher = {
            id(teacher): self._engine._build_day_slot_values(teacher)
            for teacher in self.report.teachers
        }
        day_idx_map = {day: idx for idx, day in enumerate(self.report.days)}

        for teacher in self.report.teachers:
            course = (teacher.department or "Sin curso").strip() or "Sin curso"
            if course_filter != "Todos" and course != course_filter:
                continue
            if teacher_filter and teacher.name != teacher_filter:
                continue
            slot_matrix = day_slot_values_by_teacher.get(id(teacher), [])
            for day in self.report.days:
                day_pos = day_idx_map.get(day)
                if day_pos is None or day_pos >= len(slot_matrix):
                    continue
                scheduled_slots = self._engine._scheduled_slots_for_teacher_day(teacher, day)
                if not scheduled_slots:
                    continue
                modality_slots = self._engine._modality_slots_for_teacher_day(teacher, day)
                for slot_idx in scheduled_slots:
                    schedule_name = self._schedule_name_for_slot(modality_slots, slot_idx, schedule_filter)
                    if not schedule_name:
                        continue
                    if schedule_filter != "Todos" and schedule_name != schedule_filter:
                        continue
                    if teacher_filter and schedule_filter == "Todos":
                        group = schedule_name
                    elif group_mode == "Por horario":
                        group = schedule_name
                    elif group_mode == "Por curso":
                        group = course
                    else:
                        group = teacher.name
                    slot_seconds = slot_duration_seconds(slot_idx)
                    if slot_seconds <= 0:
                        continue
                    value = slot_matrix[day_pos][slot_idx] if slot_idx < len(slot_matrix[day_pos]) else ""
                    attended, debt = self._attendance_debt_for_slot(teacher, day, slot_idx, value, slot_seconds)
                    bucket = buckets[group]
                    bucket["attendance"] = int(bucket["attendance"]) + attended
                    bucket["debt"] = int(bucket["debt"]) + debt
                    bucket["assigned"] = int(bucket["assigned"]) + slot_seconds
                    bucket["teachers"].add(teacher.name)  # type: ignore[union-attr]
                    bucket["courses"].add(course)  # type: ignore[union-attr]

        rows: list[dict[str, object]] = []
        for group, data in buckets.items():
            attendance = int(data["attendance"])
            debt = int(data["debt"])
            total = max(attendance + debt, 1)
            attendance_pct = round((attendance / total) * 100.0, 1) if attendance else 0.0
            debt_pct = round(max(100.0 - attendance_pct, 0.0), 1) if debt else 0.0
            rows.append(
                {
                    "group": group,
                    "attendance": attendance,
                    "debt": debt,
                    "assigned": int(data["assigned"]),
                    "attendance_pct": attendance_pct,
                    "debt_pct": debt_pct,
                    "teachers": len(data["teachers"]),
                    "courses": len(data["courses"]),
                }
            )
        return sorted(rows, key=lambda x: (float(x["debt_pct"]), int(x["debt"])), reverse=True)

    def _schedule_name_for_slot(self, modality_slots: dict[str, set[int]], slot_idx: int, selected: str) -> str:
        if selected != "Todos":
            return selected if slot_idx in modality_slots.get(selected, set()) else ""
        for name in sorted(modality_slots.keys(), key=str.lower):
            if slot_idx in modality_slots.get(name, set()):
                return name
        return ""

    def _attendance_debt_for_slot(
        self,
        teacher: TeacherRecord,
        day: int,
        slot_idx: int,
        value: str,
        slot_seconds: int,
    ) -> tuple[int, int]:
        if self._engine._is_non_working_day(day) or self._engine._is_suspended_block(teacher, day, slot_idx):
            return 0, slot_seconds
        if not (value or "").strip() or self._engine._is_pending_regularization_block(value):
            return 0, slot_seconds
        effective = self._engine._effective_block_seconds(value, slot_idx)
        if effective < self._engine.MIN_VALID_ATTENDANCE_MINUTES * 60:
            return 0, slot_seconds
        attended = min(effective, slot_seconds)
        return attended, max(slot_seconds - attended, 0)

    def _render_table(self, rows: list[dict[str, object]]) -> None:
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [
                str(row["group"]),
                str(row["teachers"]),
                str(row["courses"]),
                _format_hm(int(row["attendance"])),
                _format_hm(int(row["debt"])),
                _format_hm(int(row["assigned"])),
                f"{float(row['attendance_pct']):.1f}%",
                f"{float(row['debt_pct']):.1f}%",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter if col == 0 else Qt.AlignCenter)
                self.table.setItem(row_idx, col, item)
        self.table.resizeRowsToContents()

    def _render_chart(self, rows: list[dict[str, object]]) -> None:
        if not rows:
            self._set_empty("No hay datos para los filtros seleccionados.")
            return
        labels = [str(row["group"]) for row in rows]
        attendance_pct = [float(row["attendance_pct"]) for row in rows]
        debt_pct = [float(row["debt_pct"]) for row in rows]
        attendance_hours = [_format_hm(int(row["attendance"])) for row in rows]
        debt_hours = [_format_hm(int(row["debt"])) for row in rows]

        is_light = self._theme_mode == "light"
        paper = "#f3f7fb" if is_light else "#08111f"
        plot = "#ffffff" if is_light else "#0d1728"
        fg = "#0f172a" if is_light else "#eaf2ff"
        muted = "#334155" if is_light else "#d7e4f7"
        axis_text = "#0f172a" if is_light else "#f8fbff"
        grid = "rgba(15,23,42,0.08)" if is_light else "rgba(226,232,240,0.095)"
        green = "#10b981"
        green_dark = "#047857"
        green_light = "#86efac"
        red = "#fb7185" if not is_light else "#ef4444"
        red_dark = "#be123c" if not is_light else "#991b1b"
        red_light = "#ffe4e6" if not is_light else "#fecaca"

        fig = go.Figure()
        x_values = list(range(len(labels)))
        width = 0.56 if len(labels) <= 18 else 0.48
        cap_h = 3.2
        shapes: list[dict] = []

        def _ellipse_path(cx: float, cy: float, rx: float, ry: float) -> str:
            # Cubic Beziers produce a smooth oval cap for the pseudo-cylinder.
            k = 0.5522847498
            return (
                f"M {cx - rx},{cy} "
                f"C {cx - rx},{cy + k * ry} {cx - k * rx},{cy + ry} {cx},{cy + ry} "
                f"C {cx + k * rx},{cy + ry} {cx + rx},{cy + k * ry} {cx + rx},{cy} "
                f"C {cx + rx},{cy - k * ry} {cx + k * rx},{cy - ry} {cx},{cy - ry} "
                f"C {cx - k * rx},{cy - ry} {cx - rx},{cy - k * ry} {cx - rx},{cy} Z"
            )

        for idx, (att, debt) in enumerate(zip(attendance_pct, debt_pct)):
            left = idx - width / 2
            right = idx + width / 2
            center = float(idx)
            rx = width / 2
            top_att = att
            top_total = 100.0
            shapes.append(
                {
                    "type": "path",
                    "xref": "x",
                    "yref": "y",
                    "path": _ellipse_path(center + 0.04, -0.75, rx * 0.95, cap_h * 0.38),
                    "fillcolor": "rgba(15,23,42,0.14)" if is_light else "rgba(0,0,0,0.35)",
                    "line": {"width": 0},
                    "layer": "below",
                }
            )
            shapes.append(
                {
                    "type": "path",
                    "xref": "x",
                    "yref": "y",
                    "path": _ellipse_path(center, 0, rx, cap_h * 0.45),
                    "fillcolor": green_dark,
                    "line": {"color": green_light, "width": 1.1},
                    "layer": "above",
                }
            )
            if 0 < att < 100:
                shapes.append(
                    {
                        "type": "path",
                        "xref": "x",
                        "yref": "y",
                        "path": _ellipse_path(center, top_att, rx, cap_h * 0.45),
                        "fillcolor": red_light if debt > 0 else green_light,
                        "line": {"color": "rgba(255,255,255,0.65)", "width": 1.2},
                        "layer": "above",
                    }
                )
            shapes.append(
                {
                    "type": "path",
                    "xref": "x",
                    "yref": "y",
                    "path": _ellipse_path(center, top_total, rx, cap_h * 0.45),
                    "fillcolor": red_light if debt > 0 else green_light,
                    "line": {"color": "rgba(255,255,255,0.75)", "width": 1.35},
                    "layer": "above",
                }
            )
            for offset, alpha, line_w in ((-0.13, 0.22, 1.0), (0.13, 0.15, 0.9)):
                shapes.append(
                    {
                        "type": "line",
                        "xref": "x",
                        "yref": "y",
                        "x0": center + offset,
                        "x1": center + offset,
                        "y0": cap_h * 0.35,
                        "y1": top_total - cap_h * 0.35,
                        "line": {"color": f"rgba(255,255,255,{alpha})", "width": line_w},
                        "layer": "above",
                    }
                )

        fig.add_bar(
            x=x_values,
            y=attendance_pct,
            width=width,
            name="Horas asistencia",
            marker={
                "color": "rgba(16,185,129,0.94)",
                "line": {"color": "rgba(134,239,172,0.55)", "width": 0.7},
                "pattern": {"shape": ""},
            },
            hovertemplate="<b>%{customdata[1]}</b><br><span style='color:#10b981'>Asistencia</span>: %{customdata[0]}<br>%{y:.1f}%<extra></extra>",
            customdata=[[attendance_hours[idx], labels[idx]] for idx in range(len(labels))],
            text=[f"{value:.1f}%" if value >= 9 else "" for value in attendance_pct],
            textposition="inside",
            insidetextanchor="middle",
            textfont={"size": 21, "color": "#ffffff", "family": "Segoe UI Black, Arial Black, Segoe UI"},
            cliponaxis=False,
        )
        fig.add_bar(
            x=x_values,
            y=debt_pct,
            width=width,
            name="Horas deuda",
            marker={
                "color": "rgba(251,113,133,0.94)" if not is_light else "rgba(239,68,68,0.94)",
                "line": {"color": "rgba(255,228,230,0.58)", "width": 0.7},
            },
            hovertemplate="<b>%{customdata[1]}</b><br><span style='color:#fb7185'>Deuda</span>: %{customdata[0]}<br>%{y:.1f}%<extra></extra>",
            customdata=[[debt_hours[idx], labels[idx]] for idx in range(len(labels))],
            text=[f"{value:.1f}%" if value >= 9 else "" for value in debt_pct],
            textposition="inside",
            insidetextanchor="middle",
            textfont={"size": 21, "color": "#7f1d1d" if is_light else "#ffffff", "family": "Segoe UI Black, Arial Black, Segoe UI"},
            cliponaxis=False,
        )
        small_x: list[float] = []
        small_y: list[float] = []
        small_text: list[str] = []
        small_color: list[str] = []
        for idx, (att, debt) in enumerate(zip(attendance_pct, debt_pct)):
            if 0 < att < 9:
                small_x.append(idx - 0.34)
                small_y.append(max(att + 3.5, 4.5))
                small_text.append(f"{att:.1f}%")
                small_color.append(green)
                shapes.append(
                    {
                        "type": "line",
                        "xref": "x",
                        "yref": "y",
                        "x0": idx - 0.18,
                        "y0": max(att, 1.2),
                        "x1": idx - 0.32,
                        "y1": max(att + 2.8, 4.0),
                        "line": {"color": green, "width": 1.4},
                        "layer": "above",
                    }
                )
            if 0 < debt < 9:
                small_x.append(idx)
                small_y.append(104.5)
                small_text.append(f"{debt:.1f}%")
                small_color.append("#7f1d1d" if is_light else "#fff1f2")
                shapes.append(
                    {
                        "type": "line",
                        "xref": "x",
                        "yref": "y",
                        "x0": idx,
                        "y0": 100.8,
                        "x1": idx,
                        "y1": 103.2,
                        "line": {"color": red_dark, "width": 1.7},
                        "layer": "above",
                    }
                )
        if small_text:
            fig.add_scatter(
                x=small_x,
                y=small_y,
                mode="text",
                text=small_text,
                textfont={"size": 19, "color": small_color, "family": "Segoe UI Black, Arial Black, Segoe UI"},
                hoverinfo="skip",
                showlegend=False,
            )
        fig.update_layout(
            barmode="stack",
            paper_bgcolor=paper,
            plot_bgcolor=plot,
            font={"color": axis_text, "family": "Segoe UI Semibold, Segoe UI, Arial"},
            margin={"l": 58, "r": 34, "t": 36, "b": 148},
            legend={
                "orientation": "h",
                "y": -0.30,
                "x": 0.5,
                "xanchor": "center",
                "bgcolor": "rgba(0,0,0,0)",
                "font": {"size": 14, "color": axis_text, "family": "Segoe UI Black, Arial Black, Segoe UI"},
            },
            shapes=shapes,
            xaxis={
                "tickmode": "array",
                "tickvals": x_values,
                "ticktext": labels,
                "tickangle": -35,
                "gridcolor": grid,
                "zeroline": False,
                "tickfont": {"size": 12, "color": axis_text, "family": "Segoe UI Black, Arial Black, Segoe UI"},
                "linecolor": "rgba(148,163,184,0.30)",
            },
            yaxis={
                "range": [0, 112],
                "ticksuffix": "%",
                "gridcolor": grid,
                "title": {"text": "% distribucion", "font": {"size": 14, "color": axis_text, "family": "Segoe UI Black, Arial Black, Segoe UI"}},
                "tickfont": {"size": 12, "color": axis_text, "family": "Segoe UI Black, Arial Black, Segoe UI"},
                "zeroline": False,
            },
            hovermode="x unified",
            hoverlabel={
                "bgcolor": "#0f172a" if not is_light else "#ffffff",
                "bordercolor": "rgba(148,163,184,0.35)",
                "font": {"color": "#f8fafc" if not is_light else "#0f172a", "size": 14, "family": "Segoe UI Semibold, Segoe UI, Arial"},
            },
            bargap=0.34,
            uniformtext={"mode": "hide", "minsize": 12},
        )
        html = to_html(
            fig,
            include_plotlyjs="inline",
            full_html=True,
            config={
                "displaylogo": False,
                "responsive": True,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            },
        )
        html = html.replace(
            "<body>",
            f"<body style=\"margin:0;background:{paper};overflow:hidden;\">",
            1,
        )
        self._chart_html_path.parent.mkdir(parents=True, exist_ok=True)
        self._chart_html_path.write_text(html, encoding="utf-8")
        self.chart.load(QUrl.fromLocalFile(str(self._chart_html_path.resolve())))

    def _set_empty(self, message: str) -> None:
        bg = "#f8fafc" if self._theme_mode == "light" else "#0b1020"
        fg = "#0f172a" if self._theme_mode == "light" else "#e5edf7"
        self.chart.setHtml(
            f"""
            <html><body style="margin:0;background:{bg};color:{fg};font-family:Segoe UI,Arial,sans-serif;">
            <div style="height:100vh;display:flex;align-items:center;justify-content:center;">
              <div style="padding:28px 34px;border:1px solid rgba(148,163,184,.35);border-radius:20px;">
                <h2 style="margin:0 0 8px 0;">Resumen</h2>
                <p style="margin:0;color:#94a3b8;">{message}</p>
              </div>
            </div></body></html>
            """
        )

    def _apply_local_style(self) -> None:
        if self._theme_mode == "light":
            panel = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffffff, stop:1 #f1f7fd)"
            chart_bg = "#f3f7fb"
            field_bg = "#ffffff"
            field_hover = "#eef6ff"
            border = "rgba(15,23,42,0.13)"
            border_focus = "#0ea5e9"
            title = "#0f172a"
            sub = "#53657d"
            shadow = "rgba(15,23,42,0.04)"
        else:
            panel = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #101b2f, stop:1 #0b1222)"
            chart_bg = "#08111f"
            field_bg = "rgba(255,255,255,0.045)"
            field_hover = "rgba(56,189,248,0.08)"
            border = "rgba(148,163,184,0.18)"
            border_focus = "#38bdf8"
            title = "#f8fafc"
            sub = "#94a3b8"
            shadow = "rgba(0,0,0,0.18)"
        self.tab.setStyleSheet(
            f"""
            QWidget#ResumenTab {{
                background: transparent;
            }}
            QFrame#ResumenHeader {{
                background: transparent;
                border: none;
                border-radius: 0px;
                padding: 0px;
            }}
            QLabel#ResumenTitle {{
                color: {title};
                font-size: 25px;
                font-weight: 900;
                letter-spacing: 0.2px;
            }}
            QLabel#ResumenSubtitle {{
                color: {sub};
                font-size: 13px;
                font-weight: 600;
            }}
            QWebEngineView#ResumenChart {{
                background: {chart_bg};
                border: 1px solid {border};
                border-radius: 22px;
            }}
            QComboBox#ResumenField {{
                background: {field_bg};
                border: 1px solid {border};
                border-radius: 13px;
                color: {title};
                padding: 8px 34px 8px 12px;
                min-width: 150px;
                min-height: 24px;
                font-weight: 700;
            }}
            QComboBox#ResumenField:hover {{
                background: {field_hover};
                border: 1px solid {border_focus};
            }}
            QComboBox#ResumenField:focus {{
                border: 1px solid {border_focus};
            }}
            QTableWidget#ResumenTable {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 16px;
                gridline-color: {border};
            }}
            QLabel {{
                color: {sub};
                background: transparent;
            }}
            """
        )
