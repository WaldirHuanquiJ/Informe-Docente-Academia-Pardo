from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models import AttendanceReport, TeacherRecord
from app.services.horario_excel import load_horarios_workbook
from app.services.schedule_rules_cache import get_rules_with_modality
from app.services.logging_config import get_logger
from app.services.schedule_versions import resolve_schedule_for_date
from app.services.schedule_utils import (
    HEADER_NAMES,
    TIME_SLOTS,
    SLOT_START_MINUTES,
    extract_course_alias_pairs,
    extract_course_and_alias,
    extract_schedule_blocks,
    format_hm,
    norm,
    norm_name,
    scheduled_slots_for_teacher_weekday,
    slot_bounds_minutes,
    slot_duration_seconds,
    slot_index_for_block,
    slot_index_for_label,
    teacher_exists_in_schedule,
    teacher_schedule_keys,
)
from app.services.time_rules import compute_seconds_from_mark_text, split_cell_blocks
from app.ui.circular_progress import CircularProgress
from app.ui.modality_progress import ModalityProgressBar
from app.ui.reporte import ReporteView
from app.ui.engine_loader import load_ui_engine

from app.ui.attendance_view_helpers import (
    build_schedule_teachers_from_slots,
    merge_report_with_schedule_teachers,
    teacher_matches_any_alias_set,
)

dashboard_schedule_engine = load_ui_engine(__file__, "dashboard", "engine_schedule")
dashboard_metrics_engine = load_ui_engine(__file__, "dashboard", "engine_metrics")

logger = get_logger(__name__)


class DashboardView:
    MIN_VALID_ATTENDANCE_SECONDS = 3600
    DUPLICATE_MARK_WINDOW_MINUTES = 20
    EXTRA_EARLY_ROUNDING_MINUTES = 30
    EXTRA_BLOCK_MINUTES = 120

    def __init__(self, data_dir: Path) -> None:
        self.tab = QWidget()
        self._data_dir = data_dir
        self._schedule_path = self._data_dir / "HORARIOS.xlsx"
        self._schedule_aliases_by_dept: dict[str, set[str]] = {}
        self._teacher_schedule_slots: dict[str, dict[int, set[int]]] = {}
        self._schedule_teachers: list[TeacherRecord] = []
        self._day_schedule_aliases_by_dept: dict[int, dict[str, set[str]]] = {}
        self._day_teacher_schedule_slots: dict[int, dict[str, dict[int, set[int]]]] = {}
        self._day_schedule_name: dict[int, str] = {}
        self._day_teacher_modality_slots: dict[int, dict[str, dict[str, set[int]]]] = {}
        self._reporte_engine = ReporteView(data_dir)
        tab_layout = QVBoxLayout()
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)
        self.tab.setLayout(tab_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        tab_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        self.report: AttendanceReport | None = None
        self._counter_timers: list[QTimer] = []
        self._week_ranges: list[tuple[int, int, int]] = []

        self.hero_title = QLabel("Panel de Rendimiento Docente")
        self.hero_title.setProperty("role", "heroTitle")
        self.hero_title.setAlignment(Qt.AlignHCenter)
        self.hero_subtitle = QLabel("Analitica general e individual por docente")
        self.hero_subtitle.setProperty("role", "heroSubtitle")
        self.hero_subtitle.setAlignment(Qt.AlignHCenter)
        self.status_host = QWidget()
        self.status_host.setObjectName("HorarioStatusHost")
        self.status_layout = QHBoxLayout()
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_layout.setSpacing(6)
        self.status_host.setLayout(self.status_layout)

        self.teacher_selector = QComboBox()
        self.teacher_selector.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.teacher_selector.setMinimumContentsLength(24)
        self.teacher_selector.currentIndexChanged.connect(self._refresh_teacher_panel)
        self.week_selector = QComboBox()
        self.week_selector.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.week_selector.setMinimumContentsLength(18)
        self.week_selector.currentIndexChanged.connect(self._on_week_changed)
        self.week_hours_input = QDoubleSpinBox()
        self.week_hours_input.setRange(0, 200)
        self.week_hours_input.setDecimals(1)
        self.week_hours_input.setSingleStep(0.5)
        self.week_hours_input.setSuffix(" h")
        self.week_hours_input.setMaximumWidth(120)
        self.week_hours_input.setKeyboardTracking(False)
        self.week_hours_input.setReadOnly(True)
        self.week_hours_input.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.week_hours_input.setFocusPolicy(Qt.NoFocus)
        self.week_hours_input.setObjectName("weekHoursInput")
        self.save_week_hours_btn = QPushButton("Guardar")
        self.save_week_hours_btn.setMaximumWidth(90)
        self.save_week_hours_btn.setEnabled(False)
        self.save_week_hours_btn.hide()

        self.card_total_teachers = QLabel("0")
        self.card_total_courses = QLabel("0")
        self.card_teacher_marks = QLabel("0")
        self.card_teacher_rate = QLabel("0%")
        self.card_total_time = QLabel("00:00")
        self.card_total_tardiness = QLabel("00:00")
        self.card_total_absence = QLabel("00:00")
        self.card_total_extra = QLabel("00:00")
        self.card_total_extra_tardy = QLabel("00:00")
        self.card_total_early_leave = QLabel("00:00")
        self.card_total_extra_incomplete = QLabel("00:00")
        self.inline_total_teachers = QLabel("Docentes: 0")
        self.inline_total_courses = QLabel("Cursos: 0")
        self.inline_total_teachers.setProperty("role", "statChip")
        self.inline_total_courses.setProperty("role", "statChip")

        card_layout = QGridLayout()
        card_layout.setHorizontalSpacing(8)
        card_layout.setVerticalSpacing(8)
        def _make_card(title: str, value_label: QLabel, tone: int, min_height: int, big_value: bool = False) -> QWidget:
            card = QWidget()
            card.setProperty("role", "card")
            card.setProperty("tone", tone % 6)
            card.setMinimumHeight(min_height)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            inner = QVBoxLayout()
            inner.setContentsMargins(10, 8, 10, 8)
            inner.setSpacing(2)
            title_lbl = QLabel(title)
            title_lbl.setProperty("role", "cardTitle")
            title_lbl.setAlignment(Qt.AlignCenter)
            value_label.setProperty("role", "cardValue")
            value_label.setAlignment(Qt.AlignCenter)
            if big_value:
                f = value_label.font()
                f.setPointSize(max(f.pointSize() + 6, 24))
                f.setBold(True)
                value_label.setFont(f)
            inner.addWidget(title_lbl)
            inner.addWidget(value_label)
            card.setLayout(inner)
            return card

        # Tarjetas grandes (doble fila).
        big_cards = [
            ("Registros Docente", self.card_teacher_marks, 0),
            ("Cobertura Docente", self.card_teacher_rate, 1),
            ("Tiempo Docente", self.card_total_time, 2),
        ]
        for col, (title, value_label, tone) in enumerate(big_cards):
            card_layout.addWidget(_make_card(title, value_label, tone, 136, big_value=True), 0, col, 2, 1)

        # Mini tarjetas en 2 filas a la derecha.
        top_mini_cards = [
            ("Tardanza Docente", self.card_total_tardiness, 3),
            ("Horas Falta", self.card_total_absence, 4),
            ("Salida anticipada", self.card_total_early_leave, 5),
        ]
        bottom_mini_cards = [
            ("Horas Extra", self.card_total_extra, 0),
            ("Tardanza Extra", self.card_total_extra_tardy, 1),
            ("Extra incompleta", self.card_total_extra_incomplete, 2),
        ]
        for idx, (title, value_label, tone) in enumerate(top_mini_cards):
            card_layout.addWidget(_make_card(title, value_label, tone, 62), 0, 3 + idx, 1, 1)
        for idx, (title, value_label, tone) in enumerate(bottom_mini_cards):
            card_layout.addWidget(_make_card(title, value_label, tone, 62), 1, 3 + idx, 1, 1)

        self.dept_table = QTableWidget()
        self.dept_table.setColumnCount(2)
        self.dept_table.setHorizontalHeaderLabels(["Departamento", "Registros"])
        self.dept_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.dept_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.dept_table.setAlternatingRowColors(True)
        self.dept_table.setMinimumHeight(340)
        self.dept_table.verticalHeader().setDefaultSectionSize(34)
        self.dept_table.horizontalHeader().setStretchLastSection(True)
        self.dept_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.dept_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        self.top_teacher_table = QTableWidget()
        self.top_teacher_table.setColumnCount(3)
        self.top_teacher_table.setHorizontalHeaderLabels(["Docente", "Departamento", "Registros"])
        self.top_teacher_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.top_teacher_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.top_teacher_table.setAlternatingRowColors(True)
        self.top_teacher_table.setMinimumHeight(340)
        self.top_teacher_table.verticalHeader().setDefaultSectionSize(34)
        self.top_teacher_table.horizontalHeader().setStretchLastSection(True)
        self.top_teacher_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.top_teacher_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.top_teacher_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.teacher_title = QLabel("Selecciona un docente")
        self.teacher_title.setProperty("role", "teacherName")
        self.teacher_meta_id = QLabel("ID: -")
        self.teacher_meta_area = QLabel("Area: -")
        self.teacher_meta_hours = QLabel("Horas: 00:00")
        self.teacher_meta_tardiness = QLabel("Tardanza: 00:00")
        self.teacher_meta_absence = QLabel("Falta: 00:00")
        self.teacher_meta_extra = QLabel("Extra: 00:00")
        self.teacher_meta_extra_tardy = QLabel("Tardanza Extra: 00:00")
        for chip in (
            self.teacher_meta_id,
            self.teacher_meta_area,
            self.teacher_meta_hours,
            self.teacher_meta_tardiness,
            self.teacher_meta_absence,
            self.teacher_meta_extra,
            self.teacher_meta_extra_tardy,
        ):
            chip.setProperty("role", "statChip")

        self.teacher_attendance = CircularProgress("Asistencia", "#E169AF")
        self.teacher_tardiness = CircularProgress("Tardanza", "#9B6EE6")
        self.teacher_absence = CircularProgress("Faltas", "#FF4D4D")

        self.teacher_day_table = QTableWidget()
        self.teacher_day_table.setColumnCount(3)
        self.teacher_day_table.setHorizontalHeaderLabels(["Dia", "Horas", "Rendimiento"])
        self.teacher_day_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.teacher_day_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.teacher_day_table.setAlternatingRowColors(True)
        self.teacher_day_table.setMinimumHeight(360)
        self.teacher_day_table.verticalHeader().setDefaultSectionSize(36)
        self.teacher_day_table.horizontalHeader().setStretchLastSection(True)
        self.teacher_day_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.teacher_day_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.teacher_day_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.teacher_week_table = QTableWidget()
        self.teacher_week_table.setColumnCount(3)
        self.teacher_week_table.setHorizontalHeaderLabels(["Semana", "Horas", "Rendimiento"])
        self.teacher_week_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.teacher_week_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.teacher_week_table.setAlternatingRowColors(True)
        self.teacher_week_table.setMinimumHeight(360)
        self.teacher_week_table.verticalHeader().setDefaultSectionSize(36)
        self.teacher_week_table.horizontalHeader().setStretchLastSection(True)
        self.teacher_week_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.teacher_week_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.teacher_week_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.slot_progress_host = QWidget()
        self.slot_progress_host.setProperty("role", "panel")
        self.slot_progress_layout = QVBoxLayout()
        self.slot_progress_layout.setContentsMargins(8, 8, 8, 8)
        self.slot_progress_layout.setSpacing(6)
        self.slot_progress_host.setLayout(self.slot_progress_layout)
        self.progress_scope_selector = QComboBox()
        self.progress_scope_selector.addItem("Mes completo", ("month", 0))
        self.progress_scope_selector.setMinimumContentsLength(8)
        self.progress_scope_selector.setFixedHeight(24)
        self.progress_scope_selector.setStyleSheet(
            "QComboBox { border-radius: 10px; padding: 2px 8px; }"
        )
        self.progress_scope_selector.currentIndexChanged.connect(self._on_progress_scope_changed)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        hero_panel = QWidget()
        hero_layout = QVBoxLayout()
        hero_layout.setContentsMargins(0, 2, 0, 6)
        hero_layout.setSpacing(2)
        hero_layout.addWidget(self.hero_title)
        hero_layout.addWidget(self.hero_subtitle)
        hero_panel.setLayout(hero_layout)

        selector_layout = QHBoxLayout()
        selector_layout.setContentsMargins(2, 2, 2, 2)
        selector_layout.addWidget(QLabel("Docente:"))
        selector_layout.addWidget(self.teacher_selector)
        selector_layout.addWidget(QLabel("Semana:"))
        selector_layout.addWidget(self.week_selector)
        selector_layout.addWidget(QLabel("Horas/semana:"))
        selector_layout.addWidget(self.week_hours_input)
        selector_layout.addWidget(self.save_week_hours_btn)
        selector_layout.addStretch(1)
        selector_layout.addWidget(self.inline_total_teachers)
        selector_layout.addWidget(self.inline_total_courses)

        main_layout.addWidget(hero_panel)
        main_layout.addWidget(self.status_host)
        main_layout.addLayout(card_layout)
        main_layout.addLayout(selector_layout)

        rows = QHBoxLayout()
        rows.setSpacing(8)

        left_panel = QWidget()
        left_panel.setProperty("role", "panel")
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(10, 8, 10, 10)
        left_layout.setSpacing(6)
        left_layout.addWidget(self.teacher_title)
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        chips_row.addWidget(self.teacher_meta_id)
        chips_row.addWidget(self.teacher_meta_area)
        chips_row.addWidget(self.teacher_meta_hours)
        chips_row.addWidget(self.teacher_meta_tardiness)
        chips_row.addWidget(self.teacher_meta_absence)
        chips_row.addWidget(self.teacher_meta_extra)
        chips_row.addWidget(self.teacher_meta_extra_tardy)
        chips_row.addStretch(1)
        left_layout.addLayout(chips_row)
        rings_row = QHBoxLayout()
        rings_row.setSpacing(8)
        rings_row.addWidget(self.teacher_attendance)
        rings_row.addWidget(self.teacher_tardiness)
        rings_row.addWidget(self.teacher_absence)
        left_layout.addLayout(rings_row)

        tables_row = QHBoxLayout()
        tables_row.setSpacing(8)

        week_block = QVBoxLayout()
        week_block.setSpacing(4)
        week_title = QLabel("Resumen Semanal")
        week_title.setProperty("role", "panelTitle")
        week_block.addWidget(week_title)
        week_block.addWidget(self.teacher_week_table)

        day_block = QVBoxLayout()
        day_block.setSpacing(4)
        day_title = QLabel("Detalle Diario")
        day_title.setProperty("role", "panelTitle")
        day_block.addWidget(day_title)
        day_block.addWidget(self.teacher_day_table)

        progress_block = QVBoxLayout()
        progress_block.setSpacing(4)
        progress_header = QHBoxLayout()
        progress_title = QLabel("Avance por Horario")
        progress_title.setProperty("role", "panelTitle")
        progress_header.addWidget(progress_title)
        progress_header.addStretch(1)
        progress_header.addWidget(self.progress_scope_selector)
        progress_block.addLayout(progress_header)
        progress_block.addWidget(self.slot_progress_host)

        tables_row.addLayout(week_block, 2)
        tables_row.addLayout(day_block, 3)
        tables_row.addLayout(progress_block, 3)
        left_layout.addLayout(tables_row)
        left_panel.setLayout(left_layout)

        right_panel = QWidget()
        right_panel.setProperty("role", "panel")
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(10, 8, 10, 10)
        right_layout.setSpacing(6)

        right_tables_row = QHBoxLayout()
        right_tables_row.setSpacing(8)

        dept_block = QVBoxLayout()
        dept_block.setSpacing(4)
        panel_title_1 = QLabel("Distribucion por Curso")
        panel_title_1.setProperty("role", "panelTitle")
        dept_block.addWidget(panel_title_1)
        dept_block.addWidget(self.dept_table)

        rank_block = QVBoxLayout()
        rank_block.setSpacing(4)
        panel_title_2 = QLabel("Ranking de Docentes")
        panel_title_2.setProperty("role", "panelTitle")
        rank_block.addWidget(panel_title_2)
        rank_block.addWidget(self.top_teacher_table)

        right_tables_row.addLayout(dept_block, 1)
        right_tables_row.addLayout(rank_block, 1)
        right_layout.addLayout(right_tables_row)
        right_panel.setLayout(right_layout)

        rows.addWidget(left_panel, 1)
        rows.addWidget(right_panel, 1)

        main_layout.addLayout(rows)
        content.setLayout(main_layout)

    def reload_schedule_source(self) -> None:
        self._load_schedule_rules()
        self._reporte_engine.set_schedule_file(self._schedule_path)
        if self.report:
            self.refresh(self.report)

    def refresh(self, report: AttendanceReport) -> None:
        self.report = report
        self._reporte_engine.set_schedule_file(self._schedule_path)
        self._reporte_engine.set_report(report)
        self._load_schedule_rules()
        self.dept_table.setUpdatesEnabled(False)
        self.top_teacher_table.setUpdatesEnabled(False)
        teachers = [t for t in report.teachers if self._teacher_exists_in_schedule(t)]
        selector_teachers = self._merge_report_with_schedule_teachers(list(report.teachers))
        marks_per_teacher: list[tuple[TeacherRecord, int]] = []
        dept_counter: Counter[str] = Counter()

        for teacher in teachers:
            total = sum(len([segment for segment in value.split(",") if segment.strip()]) for value in teacher.marks.values())
            marks_per_teacher.append((teacher, total))
            dept_counter[teacher.department] += total

        total_teachers = len(teachers)
        total_courses = len(set(t.department for t in teachers))
        total_time_seconds = sum(self._day_total_seconds(t, day) for t in teachers for day in report.days)
        total_tardiness_seconds = sum(self._teacher_scheduled_tardiness_seconds(t, report.days) for t in teachers)

        self._animate_counter(self.card_total_teachers, total_teachers)
        self._animate_counter(self.card_total_courses, total_courses)
        self.inline_total_teachers.setText(f"Docentes: {total_teachers}")
        self.inline_total_courses.setText(f"Cursos: {total_courses}")
        versions_count = len(set(self._day_schedule_name.values())) if self._day_schedule_name else 0
        self._set_status_chips(
            [
                f"Periodo: {report.period}",
                f"Actualizado: {report.generated_date}",
                f"Docentes vinculados: {len(teachers)}/{len(report.teachers)}",
                f"Versiones de horario: {versions_count}",
            ]
        )

        self._week_ranges = self._build_week_ranges(report)
        self.week_selector.blockSignals(True)
        self.week_selector.clear()
        self.week_selector.addItem("Todo el mes", 0)
        for week_idx, start_day, end_day in self._week_ranges:
            self.week_selector.addItem(f"Semana {week_idx} ({start_day}-{end_day})", week_idx)
        self.week_selector.setCurrentIndex(0)
        self.week_selector.blockSignals(False)
        self._refresh_progress_scope_selector()

        self.teacher_selector.blockSignals(True)
        self.teacher_selector.clear()
        for teacher in sorted(selector_teachers, key=lambda t: t.name.lower()):
            self.teacher_selector.addItem(f"{teacher.name} ({teacher.teacher_id})", teacher)
        self.teacher_selector.blockSignals(False)
        if self.teacher_selector.count() > 0:
            self.teacher_selector.setCurrentIndex(0)
            self._refresh_teacher_panel()

        dept_items = dept_counter.most_common()
        self.dept_table.setRowCount(len(dept_items))
        for row_idx, (dept, count) in enumerate(dept_items):
            self.dept_table.setItem(row_idx, 0, QTableWidgetItem(dept))
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.dept_table.setItem(row_idx, 1, count_item)
        self.dept_table.resizeColumnsToContents()

        top_teachers = sorted(marks_per_teacher, key=lambda x: x[1], reverse=True)[:15]
        self.top_teacher_table.setRowCount(len(top_teachers))
        for row_idx, (teacher, count) in enumerate(top_teachers):
            self.top_teacher_table.setItem(row_idx, 0, QTableWidgetItem(teacher.name))
            self.top_teacher_table.setItem(row_idx, 1, QTableWidgetItem(teacher.department))
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.top_teacher_table.setItem(row_idx, 2, count_item)
        self.top_teacher_table.resizeColumnsToContents()

        self._refresh_teacher_panel()
        self.dept_table.setUpdatesEnabled(True)
        self.top_teacher_table.setUpdatesEnabled(True)

    def _load_schedule_rules(self) -> None:
        dashboard_schedule_engine.load_schedule_rules(self)

    def _build_schedule_teachers_from_slots(self, schedule_slots: dict[str, dict[int, set[int]]]) -> list[TeacherRecord]:
        return dashboard_schedule_engine.build_schedule_teachers_from_slots(self, schedule_slots)

    def _merge_report_with_schedule_teachers(self, csv_teachers: list[TeacherRecord]) -> list[TeacherRecord]:
        return dashboard_schedule_engine.merge_report_with_schedule_teachers(self, csv_teachers, self._schedule_teachers)

    def _extract_rules_from_workbook(
        self, xlsx_path: Path
    ) -> tuple[dict[str, set[str]], dict[str, dict[int, set[int]]]]:
        return dashboard_schedule_engine.extract_rules_from_workbook(self, xlsx_path)

    def set_schedule_file(self, schedule_path: Path) -> None:
        self._schedule_path = schedule_path

    def _teacher_exists_in_schedule(self, teacher: TeacherRecord) -> bool:
        if not self.report:
            return teacher_exists_in_schedule(teacher.name, teacher.department, self._schedule_aliases_by_dept) or self._teacher_matches_any_alias_set(teacher.name, self._schedule_aliases_by_dept)
        for day in self.report.days:
            aliases = self._aliases_for_day(day)
            if teacher_exists_in_schedule(teacher.name, teacher.department, aliases) or self._teacher_matches_any_alias_set(teacher.name, aliases):
                return True
        return False

    def _teacher_matches_any_alias_set(self, teacher_name: str, aliases_by_dept: dict[str, set[str]]) -> bool:
        return teacher_matches_any_alias_set(teacher_name, aliases_by_dept)

    def _teacher_schedule_keys(self, teacher: TeacherRecord) -> list[str]:
        return teacher_schedule_keys(teacher.teacher_id, teacher.name, teacher.department)

    def _scheduled_slots_for_teacher_weekday(self, teacher: TeacherRecord, weekday: int) -> set[int]:
        return scheduled_slots_for_teacher_weekday(
            teacher.teacher_id, teacher.name, teacher.department,
            self._teacher_schedule_slots, weekday,
        )

    def _aliases_for_day(self, day: int) -> dict[str, set[str]]:
        return self._day_schedule_aliases_by_dept.get(day, self._schedule_aliases_by_dept)

    def _slots_for_day(self, day: int) -> dict[str, dict[int, set[int]]]:
        return self._day_teacher_schedule_slots.get(day, self._teacher_schedule_slots)

    def _modality_slots_for_teacher_day(self, teacher: TeacherRecord, day: int) -> dict[str, set[int]]:
        day_map = self._day_teacher_modality_slots.get(day, {})
        result: dict[str, set[int]] = {}
        for key in self._teacher_schedule_keys(teacher):
            by_mod = day_map.get(key, {})
            for modality_name, slot_set in by_mod.items():
                result.setdefault(modality_name, set()).update(slot_set)
        return result

    def _build_day_slot_values(self, teacher: TeacherRecord, day: int) -> list[str]:
        slots = [""] * len(TIME_SLOTS)
        raw = teacher.marks.get(day, "")
        if not raw.strip():
            return slots
        scheduled_slots: set[int] = set()
        if self.report and self.report.period_start:
            try:
                weekday = self.report.period_start.replace(day=day).weekday()
                scheduled_slots = scheduled_slots_for_teacher_weekday(
                    teacher.teacher_id, teacher.name, teacher.department,
                    self._slots_for_day(day), weekday,
                )
            except ValueError:
                scheduled_slots = set()
        blocks = split_cell_blocks(raw)
        for block in blocks:
            if not block:
                continue
            pairs = self._extract_entry_exit_pairs(block)
            if not pairs:
                idx = slot_index_for_block(block)
                if idx is not None:
                    self._append_slot_value(slots, idx, "PENDIENTE")
                continue
            any_assigned = False
            for entry_min, exit_min in pairs:
                if exit_min <= entry_min:
                    continue
                assigned = False
                for slot_idx in sorted(scheduled_slots):
                    bounds = slot_bounds_minutes(slot_idx)
                    if bounds is None:
                        continue
                    slot_start, slot_end = bounds
                    overlap_start = max(entry_min, slot_start)
                    overlap_end = min(exit_min, slot_end)
                    if overlap_end <= overlap_start:
                        continue
                    self._append_slot_value(
                        slots,
                        slot_idx,
                        f"{overlap_start // 60:02d}:{overlap_start % 60:02d}\n{overlap_end // 60:02d}:{overlap_end % 60:02d}",
                    )
                    assigned = True
                    any_assigned = True
                if assigned:
                    continue
                fallback_text = f"{entry_min // 60:02d}:{entry_min % 60:02d}\n{exit_min // 60:02d}:{exit_min % 60:02d}"
                idx = slot_index_for_block(fallback_text)
                if idx is not None:
                    self._append_slot_value(slots, idx, self._normalize_extra_block_text(fallback_text))
            if any_assigned:
                continue
            idx = slot_index_for_block(block)
            if idx is not None:
                self._append_slot_value(slots, idx, self._normalize_extra_block_text(block))
        return slots

    def _day_total_seconds(self, teacher: TeacherRecord, day: int) -> int:
        return dashboard_metrics_engine.day_total_seconds(self, teacher, day)

    def _effective_block_seconds(self, block_text: str, slot_idx: int) -> int:
        return dashboard_metrics_engine.effective_block_seconds(self, block_text, slot_idx)

    def _teacher_absence_seconds(self, teacher: TeacherRecord, days: list[int]) -> int:
        return dashboard_metrics_engine.teacher_absence_seconds(self, teacher, days)

    def _is_pending_regularization_block(self, block_text: str) -> bool:
        return dashboard_metrics_engine.is_pending_regularization_block(self, block_text)

    def _teacher_expected_seconds(self, teacher: TeacherRecord, days: list[int]) -> int:
        if not self.report or not self.report.period_start:
            return 0
        total = 0
        for day in days:
            try:
                weekday = self.report.period_start.replace(day=day).weekday()
            except ValueError:
                continue
            for slot_idx in scheduled_slots_for_teacher_weekday(
                teacher.teacher_id, teacher.name, teacher.department,
                self._slots_for_day(day), weekday,
            ):
                total += slot_duration_seconds(slot_idx)
        return total

    def _teacher_extra_metrics(self, teacher: TeacherRecord, days: list[int]) -> tuple[int, int]:
        return dashboard_metrics_engine.teacher_extra_metrics(self, teacher, days)

    def _refresh_teacher_panel(self) -> None:
        if not self.report or self.teacher_selector.currentIndex() < 0:
            return
        self.teacher_day_table.setUpdatesEnabled(False)
        self.teacher_week_table.setUpdatesEnabled(False)

        teacher = self.teacher_selector.currentData()
        if not isinstance(teacher, TeacherRecord):
            return

        selected_week = int(self.week_selector.currentData() or 0)
        if selected_week > 0:
            match = next((w for w in self._week_ranges if w[0] == selected_week), None)
            if match:
                _, week_start, week_end = match
                scoped_days = [day for day in self.report.days if week_start <= day <= week_end]
            else:
                scoped_days = list(self.report.days)
        else:
            scoped_days = list(self.report.days)

        base = self._report_column_metrics(teacher, scoped_days)
        total_seconds = base["total_asistencia"]
        tardiness_seconds = base["total_tardanza"]
        absence_seconds = base["falta"]
        extra_seconds = base["horas_extra"]
        extra_tardy_seconds = base["tardanza_extra"]
        early_leave_seconds = base["salida_anticipada"]
        extra_incomplete_seconds = base["extra_incompleta"]
        expected_seconds = self._teacher_expected_seconds(teacher, scoped_days)
        auto_week_hours = expected_seconds / 3600.0
        self.week_hours_input.blockSignals(True)
        self.week_hours_input.setValue(auto_week_hours)
        self.week_hours_input.blockSignals(False)
        attendance_base = max(total_seconds + absence_seconds, 1)
        attendance_pct = min(int(round((total_seconds / attendance_base) * 100.0)), 100) if total_seconds > 0 else 0
        teacher_marks = sum(
            len([segment for segment in value.split(",") if segment.strip()])
            for day, value in teacher.marks.items()
            if day in scoped_days
        )

        tardiness_pct = self._percent_value(tardiness_seconds, max(total_seconds, 1), force_visible=True)
        absence_pct = self._percent_value(absence_seconds, attendance_base, force_visible=True)

        self.teacher_title.setText(teacher.name)
        self.teacher_meta_id.setText(f"ID: {teacher.teacher_id}")
        self.teacher_meta_area.setText(f"Area: {teacher.department}")
        self.teacher_meta_hours.setText(f"Horas: {format_hm(total_seconds)}")
        self.teacher_meta_tardiness.setText(f"Tardanza: {format_hm(tardiness_seconds)}")
        self.teacher_meta_absence.setText(f"Falta: {format_hm(absence_seconds)}")
        self.teacher_meta_extra.setText(f"Extra: {format_hm(extra_seconds)}")
        self.teacher_meta_extra_tardy.setText(f"Tardanza Extra: {format_hm(extra_tardy_seconds)}")
        self.teacher_attendance.set_value(attendance_pct)
        self.teacher_tardiness.set_value(tardiness_pct)
        self.teacher_absence.set_value(absence_pct)

        self._animate_counter(self.card_teacher_marks, teacher_marks)
        self._animate_counter(self.card_teacher_rate, attendance_pct, suffix="%")
        self.card_total_time.setText(format_hm(total_seconds))
        self.card_total_tardiness.setText(format_hm(tardiness_seconds))
        self.card_total_absence.setText(format_hm(absence_seconds))
        self.card_total_early_leave.setText(format_hm(early_leave_seconds))
        self.card_total_extra.setText(format_hm(extra_seconds))
        self.card_total_extra_tardy.setText(format_hm(extra_tardy_seconds))
        self.card_total_extra_incomplete.setText(format_hm(extra_incomplete_seconds))
        self._refresh_slot_progress(teacher, scoped_days)

        rows: list[tuple[int, int]] = []
        for day in scoped_days:
            seconds = self._day_total_seconds(teacher, day)
            if seconds > 0:
                rows.append((day, seconds))

        self.teacher_day_table.setRowCount(len(rows))
        for row_idx, (day, seconds) in enumerate(rows):
            self.teacher_day_table.setItem(row_idx, 0, QTableWidgetItem(str(day)))
            self.teacher_day_table.setItem(row_idx, 1, QTableWidgetItem(format_hm(seconds)))
            perf = min(int((seconds / (2 * 3600)) * 100), 100)
            perf_item = QTableWidgetItem(f"{perf}%")
            perf_item.setTextAlignment(Qt.AlignCenter)
            self.teacher_day_table.setItem(row_idx, 2, perf_item)
        self.teacher_day_table.resizeColumnsToContents()

        weekly_buckets: dict[int, int] = {}
        for day in scoped_days:
            seconds = self._day_total_seconds(teacher, day)
            if seconds <= 0:
                continue
            week_index = self._week_index_for_day(day)
            weekly_buckets[week_index] = weekly_buckets.get(week_index, 0) + seconds

        weekly_items = sorted(weekly_buckets.items())
        self.teacher_week_table.setRowCount(len(weekly_items))
        for row_idx, (week_idx, seconds) in enumerate(weekly_items):
            self.teacher_week_table.setItem(row_idx, 0, QTableWidgetItem(f"Semana {week_idx}"))
            self.teacher_week_table.setItem(row_idx, 1, QTableWidgetItem(format_hm(seconds)))
            week_match = next((w for w in self._week_ranges if w[0] == week_idx), None)
            if week_match:
                _, week_start, week_end = week_match
                week_days = [d for d in scoped_days if week_start <= d <= week_end]
                expected = self._teacher_expected_seconds(teacher, week_days)
            else:
                expected = 0
            perf = min(int((seconds / expected) * 100), 100) if expected else 0
            perf_item = QTableWidgetItem(f"{perf}%")
            perf_item.setTextAlignment(Qt.AlignCenter)
            self.teacher_week_table.setItem(row_idx, 2, perf_item)
        self.teacher_week_table.resizeColumnsToContents()
        self.teacher_day_table.setUpdatesEnabled(True)
        self.teacher_week_table.setUpdatesEnabled(True)

    def _report_column_metrics(self, teacher: TeacherRecord, days: list[int]) -> dict[str, int]:
        return dashboard_metrics_engine.report_column_metrics(self, teacher, days)

    def _percent_value(self, numerator_seconds: int, denominator_seconds: int, force_visible: bool = False) -> int:
        if denominator_seconds <= 0 or numerator_seconds <= 0:
            return 0
        raw = (numerator_seconds / denominator_seconds) * 100.0
        pct = min(int(round(raw)), 100)
        if force_visible and pct == 0:
            return 1
        return pct

    def _build_week_ranges(self, report: AttendanceReport) -> list[tuple[int, int, int]]:
        if not report.days:
            return []
        if not report.period_start:
            max_day = max(report.days)
            total_weeks = ((max_day - 1) // 7) + 1
            return [(idx, ((idx - 1) * 7) + 1, min(idx * 7, max_day)) for idx in range(1, total_weeks + 1)]

        month_days = sorted(report.days)
        ranges: list[tuple[int, int, int]] = []
        week_idx = 1
        start_day = month_days[0]
        prev_day = month_days[0]

        for day in month_days:
            current_date = report.period_start.replace(day=day)
            if day != start_day and current_date.weekday() == 6:
                ranges.append((week_idx, start_day, prev_day))
                week_idx += 1
                start_day = day
            prev_day = day

        ranges.append((week_idx, start_day, prev_day))
        return ranges

    def _teacher_scheduled_tardiness_seconds(self, teacher: TeacherRecord, days: list[int]) -> int:
        if not self.report or not self.report.period_start:
            return 0
        total = 0
        for day in days:
            day_slots = self._build_day_slot_values(teacher, day)
            try:
                weekday = self.report.period_start.replace(day=day).weekday()
            except ValueError:
                continue
            scheduled = scheduled_slots_for_teacher_weekday(
                teacher.teacher_id, teacher.name, teacher.department,
                self._slots_for_day(day), weekday,
            )
            for slot_idx in scheduled:
                if not (0 <= slot_idx < len(day_slots)):
                    continue
                value = day_slots[slot_idx]
                if not value.strip() or self._is_pending_regularization_block(value):
                    continue
                if self._effective_block_seconds(value, slot_idx) < self.MIN_VALID_ATTENDANCE_SECONDS:
                    continue
                entry = self._first_time_minutes(value)
                bounds = slot_bounds_minutes(slot_idx)
                if entry is None or bounds is None:
                    continue
                start_min, _ = bounds
                tardy_seconds = max(entry - start_min, 0) * 60
                slot_cap = slot_duration_seconds(slot_idx)
                if slot_cap > 0:
                    tardy_seconds = min(tardy_seconds, slot_cap)
                total += tardy_seconds
        return total

    def _first_time_minutes(self, text: str) -> int | None:
        match = re.search(r"([01]?\d|2[0-3]):([0-5]\d)", text or "")
        if not match:
            return None
        return int(match.group(1)) * 60 + int(match.group(2))

    def _extra_block_metrics(self, block_text: str) -> tuple[int, int]:
        minutes = self._normalized_event_minutes(block_text)
        if len(minutes) < 2:
            return 0, 0
        total_seconds = 0
        total_tardy_seconds = 0
        for idx in range(0, len(minutes) - 1, 2):
            entry_real = minutes[idx]
            exit_real = minutes[idx + 1]
            if exit_real <= entry_real:
                continue
            expected_start = (entry_real // 60) * 60
            next_hour = expected_start + 60
            if (next_hour - entry_real) <= self.EXTRA_EARLY_ROUNDING_MINUTES:
                entry_adjusted = next_hour
                tardy_seconds = 0
            else:
                entry_adjusted = entry_real
                tardy_seconds = max(entry_real - expected_start, 0) * 60
            if exit_real <= entry_adjusted:
                continue
            first_boundary = entry_adjusted + self.EXTRA_BLOCK_MINUTES
            if exit_real < first_boundary:
                exit_adjusted = exit_real
            else:
                steps = (exit_real - entry_adjusted) // self.EXTRA_BLOCK_MINUTES
                exit_adjusted = entry_adjusted + (steps * self.EXTRA_BLOCK_MINUTES)
            if exit_adjusted <= entry_adjusted:
                continue
            total_seconds += (exit_adjusted - entry_adjusted) * 60
            total_tardy_seconds += tardy_seconds
        return total_seconds, total_tardy_seconds

    def _normalize_extra_block_text(self, block_text: str) -> str:
        minutes = self._normalized_event_minutes(block_text)
        if len(minutes) < 2:
            return block_text
        lines: list[str] = []
        for idx in range(0, len(minutes) - 1, 2):
            entry_real = minutes[idx]
            exit_real = minutes[idx + 1]
            if exit_real <= entry_real:
                continue
            expected_start = (entry_real // 60) * 60
            next_hour = expected_start + 60
            entry_adjusted = next_hour if (next_hour - entry_real) <= self.EXTRA_EARLY_ROUNDING_MINUTES else entry_real
            first_boundary = entry_adjusted + self.EXTRA_BLOCK_MINUTES
            if exit_real < first_boundary:
                exit_adjusted = exit_real
            else:
                steps = (exit_real - entry_adjusted) // self.EXTRA_BLOCK_MINUTES
                exit_adjusted = entry_adjusted + (steps * self.EXTRA_BLOCK_MINUTES)
            if exit_adjusted <= entry_adjusted:
                continue
            lines.append(f"{entry_adjusted // 60:02d}:{entry_adjusted % 60:02d}")
            lines.append(f"{exit_adjusted // 60:02d}:{exit_adjusted % 60:02d}")
        return "\n".join(lines) if lines else block_text

    def _append_slot_value(self, slots: list[str], idx: int, text: str) -> None:
        if not (0 <= idx < len(slots)):
            return
        value = (text or "").strip()
        if not value:
            return
        current = (slots[idx] or "").strip()
        if not current:
            slots[idx] = value
            return
        parts = split_cell_blocks(current)
        if value in parts:
            return
        slots[idx] = f"{current}\n_____\n{value}"

    def _extract_entry_exit_pairs(self, block_text: str) -> list[tuple[int, int]]:
        minutes = self._normalized_event_minutes(block_text)
        if len(minutes) < 2:
            return []
        return [(minutes[i], minutes[i + 1]) for i in range(0, len(minutes) - 1, 2)]

    def _normalized_event_minutes(self, block_text: str) -> list[int]:
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
            while end + 1 < len(raw) and (raw[end + 1] - raw[end]) <= self.DUPLICATE_MARK_WINDOW_MINUTES:
                end += 1
            normalized.append(raw[start] if is_entry else raw[end])
            idx = end + 1
            is_entry = not is_entry
        return normalized

    def _teacher_early_departure_seconds(self, teacher: TeacherRecord, days: list[int]) -> int:
        if not self.report or not self.report.period_start:
            return 0
        total = 0
        for day in days:
            try:
                weekday = self.report.period_start.replace(day=day).weekday()
            except ValueError:
                continue
            scheduled = scheduled_slots_for_teacher_weekday(
                teacher.teacher_id, teacher.name, teacher.department,
                self._slots_for_day(day), weekday,
            )
            if not scheduled:
                continue
            day_slots = self._build_day_slot_values(teacher, day)
            for slot_idx in scheduled:
                value = day_slots[slot_idx] if 0 <= slot_idx < len(day_slots) else ""
                if not value.strip():
                    continue
                times = re.findall(r"([01]?\d|2[0-3]):([0-5]\d)", value or "")
                if len(times) < 2:
                    continue
                bounds = slot_bounds_minutes(slot_idx)
                if bounds is None:
                    continue
                _, slot_end = bounds
                try:
                    exit_min = int(times[-1][0]) * 60 + int(times[-1][1])
                except Exception:
                    continue
                if exit_min < slot_end:
                    total += (slot_end - exit_min) * 60
        return total

    def _teacher_extra_incomplete_seconds(self, teacher: TeacherRecord, days: list[int]) -> int:
        if not self.report or not self.report.period_start:
            return 0
        total = 0
        for day in days:
            try:
                weekday = self.report.period_start.replace(day=day).weekday()
            except ValueError:
                continue
            scheduled = scheduled_slots_for_teacher_weekday(
                teacher.teacher_id, teacher.name, teacher.department,
                self._slots_for_day(day), weekday,
            )
            day_slots = self._build_day_slot_values(teacher, day)
            for slot_idx, value in enumerate(day_slots):
                if not value.strip() or slot_idx in scheduled:
                    continue
                times = re.findall(r"([01]?\d|2[0-3]):([0-5]\d)", value or "")
                if len(times) < 2:
                    continue
                try:
                    entry_min = int(times[0][0]) * 60 + int(times[0][1])
                    exit_min = int(times[-1][0]) * 60 + int(times[-1][1])
                except Exception:
                    continue
                if exit_min <= entry_min:
                    continue
                base_start = (entry_min // 60) * 60
                expected_end = base_start + 120
                if exit_min < expected_end:
                    total += (expected_end - exit_min) * 60
        return total

    def _week_index_for_day(self, day: int) -> int:
        for idx, start_day, end_day in self._week_ranges:
            if start_day <= day <= end_day:
                return idx
        return 1

    def _animate_counter(self, label: QLabel, target: int, suffix: str = "") -> None:
        target = max(0, int(target))
        timer = QTimer(label)
        self._counter_timers.append(timer)

        steps = 18
        step_value = max(1, target // steps) if target else 1
        state = {"value": 0}

        def tick() -> None:
            state["value"] += step_value
            if state["value"] >= target:
                label.setText(f"{target}{suffix}")
                timer.stop()
                if timer in self._counter_timers:
                    self._counter_timers.remove(timer)
                return
            label.setText(f"{state['value']}{suffix}")

        timer.timeout.connect(tick)
        timer.start(16)

    def _selected_week_key(self) -> str:
        selected_week = int(self.week_selector.currentData() or 0)
        base = "month" if selected_week == 0 else f"week_{selected_week}"
        if self.report and self.report.period_start:
            period_key = f"{self.report.period_start.year}-{self.report.period_start.month:02d}"
            return f"{period_key}:{base}"
        return base

    def _period_prefix(self) -> str:
        if self.report and self.report.period_start:
            return f"{self.report.period_start.year}-{self.report.period_start.month:02d}"
        return "period"

    def _on_week_changed(self) -> None:
        self._sync_week_selectors(from_week_selector=True)
        self._refresh_teacher_panel()

    def _on_progress_scope_changed(self) -> None:
        self._sync_week_selectors(from_week_selector=False)
        self._refresh_teacher_panel()

    def _sync_week_selectors(self, from_week_selector: bool) -> None:
        if from_week_selector:
            selected_week = int(self.week_selector.currentData() or 0)
            idx = self._progress_scope_index_for_week(selected_week)
            if idx >= 0 and self.progress_scope_selector.currentIndex() != idx:
                self.progress_scope_selector.blockSignals(True)
                self.progress_scope_selector.setCurrentIndex(idx)
                self.progress_scope_selector.blockSignals(False)
            return

        data = self.progress_scope_selector.currentData() or ("month", 0)
        if isinstance(data, tuple) and len(data) == 2:
            mode, week_idx = data
        else:
            mode, week_idx = "month", 0
        target_week = 0 if mode == "month" else int(week_idx or 0)
        idx = self._week_selector_index_for_week(target_week)
        if idx >= 0 and self.week_selector.currentIndex() != idx:
            self.week_selector.blockSignals(True)
            self.week_selector.setCurrentIndex(idx)
            self.week_selector.blockSignals(False)

    def _progress_scope_index_for_week(self, week_idx: int) -> int:
        for i in range(self.progress_scope_selector.count()):
            data = self.progress_scope_selector.itemData(i)
            if isinstance(data, tuple) and len(data) == 2:
                mode, val = data
                if week_idx == 0 and str(mode) == "month":
                    return i
                if week_idx > 0 and str(mode) == "week" and int(val or 0) == week_idx:
                    return i
        return -1

    def _week_selector_index_for_week(self, week_idx: int) -> int:
        for i in range(self.week_selector.count()):
            if int(self.week_selector.itemData(i) or 0) == week_idx:
                return i
        return -1

    def _refresh_progress_scope_selector(self) -> None:
        target_week = int(self.week_selector.currentData() or 0)
        self.progress_scope_selector.blockSignals(True)
        self.progress_scope_selector.clear()
        self.progress_scope_selector.addItem("Mes completo", ("month", 0))
        for week_idx, start_day, end_day in self._week_ranges:
            self.progress_scope_selector.addItem(
                f"Semana {week_idx} ({start_day}-{end_day})",
                ("week", week_idx),
            )
        idx = self._progress_scope_index_for_week(target_week)
        self.progress_scope_selector.setCurrentIndex(idx if idx >= 0 else 0)
        self.progress_scope_selector.blockSignals(False)

    def _refresh_slot_progress(self, teacher: TeacherRecord, scoped_days: list[int]) -> None:
        while self.slot_progress_layout.count():
            item = self.slot_progress_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self.report or not self.report.period_start:
            return
        data = self.progress_scope_selector.currentData() or ("month", 0)
        if isinstance(data, tuple) and len(data) == 2:
            mode, week_idx = data
        else:
            mode, week_idx = "month", 0
        if mode == "month":
            days_for_progress = list(self.report.days)
        else:
            match = next((w for w in self._week_ranges if w[0] == int(week_idx)), None)
            if match:
                _, week_start, week_end = match
                days_for_progress = [d for d in self.report.days if week_start <= d <= week_end]
            else:
                days_for_progress = list(scoped_days)
        if not days_for_progress:
            days_for_progress = list(self.report.days)

        modality_acc: dict[str, tuple[int, int]] = {}
        for day in days_for_progress:
            day_slots = self._build_day_slot_values(teacher, day)
            by_modality = self._modality_slots_for_teacher_day(teacher, day)
            for modality_name, slot_indices in by_modality.items():
                expected = 0
                attended = 0
                for slot_idx in sorted(slot_indices):
                    expected += slot_duration_seconds(slot_idx)
                    block = day_slots[slot_idx] if 0 <= slot_idx < len(day_slots) else ""
                    attended += min(self._effective_block_seconds(block, slot_idx), slot_duration_seconds(slot_idx))
                prev_expected, prev_attended = modality_acc.get(modality_name, (0, 0))
                modality_acc[modality_name] = (prev_expected + expected, prev_attended + attended)

        for modality_name, (expected, attended) in sorted(modality_acc.items(), key=lambda x: x[0].lower()):
            if expected <= 0:
                continue
            pct = min(int((attended / expected) * 100), 100)
            widget = ModalityProgressBar(
                title_text=modality_name,
                progress_text=f"{pct}%  ({format_hm(attended)} / {format_hm(expected)})",
                percent=pct,
            )
            self.slot_progress_layout.addWidget(widget)
        if modality_acc:
            self.slot_progress_layout.addStretch(1)
            return

        for slot_idx, slot_label in enumerate(TIME_SLOTS):
            expected = 0
            attended = 0
            for day in days_for_progress:
                try:
                    weekday = self.report.period_start.replace(day=day).weekday()
                except ValueError:
                    continue
                scheduled = scheduled_slots_for_teacher_weekday(
                    teacher.teacher_id, teacher.name, teacher.department,
                    self._slots_for_day(day), weekday,
                )
                if slot_idx not in scheduled:
                    continue
                expected += slot_duration_seconds(slot_idx)
                day_slots = self._build_day_slot_values(teacher, day)
                block = day_slots[slot_idx] if 0 <= slot_idx < len(day_slots) else ""
                attended += min(self._effective_block_seconds(block, slot_idx), slot_duration_seconds(slot_idx))

            if expected <= 0:
                continue
            pct = min(int((attended / expected) * 100), 100)
            widget = ModalityProgressBar(
                title_text=f"Horario {slot_idx + 1}: {slot_label}",
                progress_text=f"{pct}%  ({format_hm(attended)} / {format_hm(expected)})",
                percent=pct,
            )
            self.slot_progress_layout.addWidget(widget)
        self.slot_progress_layout.addStretch(1)

    def _set_status_chips(self, items: list[str]) -> None:
        while self.status_layout.count():
            item = self.status_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for text in items:
            chip = QLabel(text)
            chip.setObjectName("HorarioStatusChip")
            chip.setAlignment(Qt.AlignCenter)
            self.status_layout.addWidget(chip)
        self.status_layout.addStretch(1)

    def clear_all(self) -> None:
        self.report = None
        self.teacher_selector.clear()
        self.week_selector.clear()
        self.progress_scope_selector.clear()
        self.progress_scope_selector.addItem("Mes completo", ("month", 0))
        self.dept_table.setRowCount(0)
        self.top_teacher_table.setRowCount(0)
        self.teacher_day_table.setRowCount(0)
        self.teacher_week_table.setRowCount(0)
        self.teacher_title.setText("Selecciona un docente")
        self.teacher_meta_id.setText("ID: -")
        self.teacher_meta_area.setText("Area: -")
        self.teacher_meta_hours.setText("Horas: 00:00")
        self.teacher_meta_tardiness.setText("Tardanza: 00:00")
        self.teacher_meta_absence.setText("Falta: 00:00")
        self.teacher_meta_extra.setText("Extra: 00:00")
        self.teacher_meta_extra_tardy.setText("Tardanza Extra: 00:00")
        self.teacher_attendance.set_value(0)
        self.teacher_tardiness.set_value(0)
        self.teacher_absence.set_value(0)
        self.card_total_teachers.setText("0")
        self.card_total_courses.setText("0")
        self.card_teacher_marks.setText("0")
        self.card_teacher_rate.setText("0%")
        self.card_total_time.setText("00:00")
        self.card_total_tardiness.setText("00:00")
        self.card_total_absence.setText("00:00")
        self.card_total_early_leave.setText("00:00")
        self.card_total_extra.setText("00:00")
        self.card_total_extra_tardy.setText("00:00")
        self.card_total_extra_incomplete.setText("00:00")
        self.inline_total_teachers.setText("Docentes: 0")
        self.inline_total_courses.setText("Cursos: 0")
        while self.slot_progress_layout.count():
            item = self.slot_progress_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        while self.status_layout.count():
            item = self.status_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
