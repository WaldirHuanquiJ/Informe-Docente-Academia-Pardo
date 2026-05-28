from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QHeaderView,
    QFrame,
)

from app.models import TeacherRecord, AttendanceReport
from app.services.logging_config import get_logger
from app.services.pdf_generator import generate_teacher_pdf
from app.services.schedule_utils import (
    TIME_SLOTS,
    SLOT_START_MINUTES,
    extract_course_alias_pairs,
    extract_course_and_alias,
    extract_schedule_blocks,
    extract_schedule_blocks_with_continuity,
    format_hm,
    norm_name,
    scheduled_slots_for_teacher_weekday,
    slot_duration_seconds,
    slot_bounds_minutes,
    slot_index_for_block,
    slot_index_for_label,
    teacher_exists_in_schedule,
    teacher_schedule_keys,
)
from app.services.time_rules import (
    compute_seconds_from_mark_text,
    split_cell_blocks,
)
from app.services.horario_excel import load_horarios_workbook
from app.services.schedule_rules_cache import get_rules_with_modality
from app.services.schedule_versions import resolve_schedule_for_date
from PySide6.QtPrintSupport import QPrinterInfo, QPrinter
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions
from app.ui.print_dialog import PrintDialog, PrintOptions
from app.ui.icon_factory import (
    make_export_icon,
    make_export_all_icon,
    make_print_icon,
    make_print_all_icon,
)
from app.services.session_store import load_session, save_session
from app.ui.attendance_view_helpers import (
    build_schedule_teachers_from_slots,
    merge_report_with_schedule_teachers,
    teacher_matches_any_alias_set,
)
from app.ui.reporte import ReporteView
from app.ui.engine_loader import load_ui_engine

informe_metrics_engine = load_ui_engine(__file__, "informe", "engine_metrics")
informe_attendance_engine = load_ui_engine(__file__, "informe", "engine_attendance")
informe_tables_engine = load_ui_engine(__file__, "informe", "engine_tables")

logger = get_logger(__name__)


class InformeView:
    MIN_VALID_ATTENDANCE_SECONDS = ReporteView.MIN_VALID_ATTENDANCE_MINUTES * 60
    DUPLICATE_MARK_WINDOW_MINUTES = 20
    EXTRA_EARLY_ROUNDING_MINUTES = 30
    EXTRA_BLOCK_MINUTES = 120
    OUT_OF_SCHEDULE_GRACE_MINUTES = 5
    OUT_OF_SCHEDULE_MIN_BLOCK_MINUTES = 60
    _SESSION_KEY_EXPORT_PDF_DIR = "last_export_pdf_dir"
    _SESSION_KEY_EXPORT_ALL_DIR = "last_export_all_dir"

    def __init__(self, data_dir: Path) -> None:
        self.tab = QWidget()
        self._data_dir = data_dir
        self._exports_dir = self._data_dir.parent
        self._print_spool_dir = self._data_dir / "_print_spool"
        self._schedule_path = self._data_dir / "HORARIOS.xlsx"
        self._reporte_engine = ReporteView(data_dir)
        self._schedule_aliases_by_dept: dict[str, set[str]] = {}
        self._teacher_schedule_slots: dict[str, dict[int, set[int]]] = {}
        self._schedule_teachers: list[TeacherRecord] = []
        self._day_schedule_aliases_by_dept: dict[int, dict[str, set[str]]] = {}
        self._day_teacher_schedule_slots: dict[int, dict[str, dict[int, set[int]]]] = {}
        self._day_teacher_modality_slots: dict[int, dict[str, dict[str, set[int]]]] = {}
        self.report: AttendanceReport | None = None
        self._report_teachers_all: list[TeacherRecord] = []
        self._preferred_printer: str = ""
        self._last_print_options: PrintOptions | None = None
        self._theme_mode: str = "dark"

        # ── Encabezado ───────────────────────────────────────────────────
        self.hero_title = QLabel("Informe Individual Docente")
        self.hero_title.setProperty("role", "heroTitle")
        self.hero_title.setAlignment(Qt.AlignHCenter)
        self.hero_subtitle = QLabel("Vista previa completa del documento PDF a exportar")
        self.hero_subtitle.setProperty("role", "heroSubtitle")
        self.hero_subtitle.setAlignment(Qt.AlignHCenter)

        # ── Controles ────────────────────────────────────────────────────
        self.teacher_selector = QComboBox()
        self.teacher_selector.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.teacher_selector.setMinimumContentsLength(24)
        self.teacher_selector.currentIndexChanged.connect(self._on_teacher_changed)

        self.export_button = QPushButton("Exportar PDF")
        self.export_button.setMaximumWidth(180)
        self.export_button.setObjectName("actionExport")
        export_icon = make_export_icon(20)
        export_all_icon = make_export_all_icon(20)
        print_icon = make_print_icon(20)
        print_all_icon = make_print_all_icon(20)
        self.export_button.setIcon(export_icon)
        self.export_button.clicked.connect(self._on_export_clicked)
        self.export_button.setEnabled(False)

        self.export_all_button = QPushButton("Exportar Todos")
        self.export_all_button.setMaximumWidth(200)
        self.export_all_button.setObjectName("actionExportAll")
        self.export_all_button.setIcon(export_all_icon)
        self.export_all_button.clicked.connect(self._on_export_all_clicked)
        self.export_all_button.setEnabled(False)

        self.print_button = QPushButton("Imprimir")
        self.print_button.setMaximumWidth(150)
        self.print_button.setObjectName("actionPrint")
        self.print_button.setIcon(print_icon)
        self.print_button.clicked.connect(self._on_print_clicked)
        self.print_button.setEnabled(False)

        self.print_all_button = QPushButton("Imprimir Todos")
        self.print_all_button.setMaximumWidth(180)
        self.print_all_button.setObjectName("actionPrintAll")
        self.print_all_button.setIcon(print_all_icon)
        self.print_all_button.clicked.connect(self._on_print_all_clicked)
        self.print_all_button.setEnabled(False)
        self.export_button.setIconSize(QSize(20, 20))
        self.export_all_button.setIconSize(QSize(20, 20))
        self.print_button.setIconSize(QSize(20, 20))
        self.print_all_button.setIconSize(QSize(20, 20))
        self._apply_rounded_buttons(
            self.export_button,
            self.export_all_button,
            self.print_button,
            self.print_all_button,
        )

        # ── Info del docente ─────────────────────────────────────────────
        self.docente_nombre = QLabel("—")
        self.docente_nombre.setProperty("role", "teacherName")
        self.docente_id = QLabel("ID: —")
        self.docente_depto = QLabel("Depto: —")
        self.docente_periodo = QLabel("Periodo: —")
        for chip in (self.docente_id, self.docente_depto, self.docente_periodo):
            chip.setProperty("role", "statChip")

        # ── Cards KPI ────────────────────────────────────────────────────
        self.card_horas = QLabel("00:00")
        self.card_asistencia = QLabel("0%")
        self.card_tardanza = QLabel("00:00")
        self.card_faltas = QLabel("00:00")
        self.card_extra = QLabel("00:00")
        self.card_extra_tardy = QLabel("00:00")
        self.card_dias = QLabel("00:00")
        self.card_esperadas = QLabel("00:00")
        self.card_cumplimiento = QLabel("0%")
        self.card_pendientes = QLabel("0")
        self.card_bloques = QLabel("0/0")
        self.card_inasistencias = QLabel("0")

        kpi_cards = [
            # Fila 1, columnas 1-4: programadas
            ("Horas Asistidas", self.card_horas, 0, 0, 0),
            ("% Asistencia", self.card_asistencia, 1, 0, 1),
            ("Tardanza", self.card_tardanza, 2, 0, 2),
            ("Salida anticipada", self.card_dias, 6, 0, 3),
            # Fila 2, columnas 1-4: extras
            ("Horas Extra", self.card_extra, 4, 2, 0),
            ("Tardanza Extra", self.card_extra_tardy, 5, 2, 1),
            ("Extra incompleta", self.card_esperadas, 5, 2, 2),
            ("Horas Falta", self.card_faltas, 3, 2, 3),
            # Columnas 5-6: otros indicadores (ambas filas)
            ("Cumplimiento horario", self.card_cumplimiento, 1, 0, 5),
            ("Pendientes regulariz.", self.card_pendientes, 2, 0, 6),
            ("Bloques cumplidos", self.card_bloques, 0, 2, 5),
            ("Inasistencias", self.card_inasistencias, 3, 2, 6),
        ]

        self.kpi_grid = QGridLayout()
        self.kpi_grid.setHorizontalSpacing(8)
        self.kpi_grid.setVerticalSpacing(8)
        for title, value_label, tone, row, col in kpi_cards:
            card = QWidget()
            card.setProperty("role", "card")
            card.setProperty("tone", tone)
            card.setMinimumHeight(92)
            card.setMaximumHeight(92)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            inner = QVBoxLayout()
            inner.setContentsMargins(10, 8, 10, 8)
            inner.setSpacing(2)
            title_lbl = QLabel(title)
            title_lbl.setProperty("role", "cardTitle")
            title_lbl.setAlignment(Qt.AlignCenter)
            value_label.setProperty("role", "cardValue")
            value_label.setAlignment(Qt.AlignCenter)
            inner.addWidget(title_lbl)
            inner.addWidget(value_label)
            card.setLayout(inner)
            if title == "Horas Falta":
                # Resaltar visualmente "Horas Falta" para separarlo del bloque.
                card.setObjectName("cardHorasFalta")
                card.setStyleSheet(
                    "QWidget#cardHorasFalta {"
                    " border: 1px solid rgba(220, 38, 38, 0.45);"
                    " border-radius: 12px;"
                    " }"
                )
            self.kpi_grid.addWidget(card, row, col)

        # Separador horizontal entre fila 1 y fila 2 en columnas 1-4.
        self.kpi_row_separator = QFrame()
        self.kpi_row_separator.setFrameShape(QFrame.HLine)
        self.kpi_row_separator.setFrameShadow(QFrame.Plain)
        self.kpi_row_separator.setObjectName("kpiRowSeparator")
        self.kpi_row_separator.setMinimumHeight(10)
        self.kpi_row_separator.setMaximumHeight(10)
        self.kpi_row_separator.setStyleSheet(
            "QFrame#kpiRowSeparator {"
            " color: rgba(120, 130, 150, 0.42);"
            " background: transparent;"
            " }"
        )
        self.kpi_grid.addWidget(self.kpi_row_separator, 1, 0, 1, 4)

        # Separador visual profesional entre columnas 4 y 5.
        self.kpi_separator = QFrame()
        self.kpi_separator.setFrameShape(QFrame.VLine)
        self.kpi_separator.setFrameShadow(QFrame.Plain)
        self.kpi_separator.setObjectName("kpiColumnSeparator")
        self.kpi_separator.setMinimumWidth(12)
        self.kpi_separator.setMaximumWidth(12)
        self.kpi_separator.setStyleSheet(
            "QFrame#kpiColumnSeparator {"
            " color: rgba(120, 130, 150, 0.45);"
            " background: transparent;"
            " }"
        )
        self.kpi_grid.addWidget(self.kpi_separator, 0, 4, 3, 1)

        for c in (0, 1, 2, 3, 5, 6):
            self.kpi_grid.setColumnStretch(c, 1)
        self.kpi_grid.setColumnStretch(4, 0)
        self.kpi_grid.setColumnMinimumWidth(4, 12)
        self.kpi_grid.setRowStretch(0, 1)
        self.kpi_grid.setRowStretch(1, 0)
        self.kpi_grid.setRowStretch(2, 1)

        # ── Tabla diaria ─────────────────────────────────────────────────
        self.daily_table = QTableWidget()
        self.daily_table.setObjectName("HorarioTable")
        self.daily_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.daily_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.daily_table.setShowGrid(False)
        self.daily_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        # ── Tabla semanal ────────────────────────────────────────────────
        self.weekly_table = QTableWidget()
        self.weekly_table.setObjectName("HorarioTable")
        self.weekly_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.weekly_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.weekly_table.setShowGrid(False)
        self.weekly_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        # ── Layout scrollable ────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        hero_panel = QWidget()
        hero_layout = QVBoxLayout()
        hero_layout.setContentsMargins(0, 2, 0, 6)
        hero_layout.setSpacing(2)
        hero_layout.addWidget(self.hero_title)
        hero_layout.addWidget(self.hero_subtitle)
        hero_panel.setLayout(hero_layout)
        main_layout.addWidget(hero_panel)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Docente:"))
        controls.addWidget(self.teacher_selector)
        controls.addWidget(self.export_button)
        controls.addWidget(self.print_button)
        controls.addWidget(self.export_all_button)
        controls.addWidget(self.print_all_button)
        controls.addStretch(1)
        main_layout.addLayout(controls)

        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        info_row.addWidget(self.docente_nombre)
        info_row.addWidget(self.docente_id)
        info_row.addWidget(self.docente_depto)
        info_row.addWidget(self.docente_periodo)
        info_row.addStretch(1)
        main_layout.addLayout(info_row)

        main_layout.addLayout(self.kpi_grid)

        tables_row = QHBoxLayout()
        tables_row.setSpacing(8)

        daily_block = QVBoxLayout()
        daily_section = QLabel("DETALLE DIARIO DE ASISTENCIA")
        daily_section.setProperty("role", "panelTitle")
        daily_section.setAlignment(Qt.AlignLeft)
        daily_block.addWidget(daily_section)
        daily_block.addWidget(self.daily_table)

        weekly_block = QVBoxLayout()
        weekly_section = QLabel("RESUMEN SEMANAL")
        weekly_section.setProperty("role", "panelTitle")
        weekly_section.setAlignment(Qt.AlignLeft)
        weekly_block.addWidget(weekly_section)
        weekly_block.addWidget(self.weekly_table)

        tables_row.addLayout(daily_block, 3)
        tables_row.addLayout(weekly_block, 2)
        main_layout.addLayout(tables_row)

        content.setLayout(main_layout)
        scroll.setWidget(content)

        tab_layout = QVBoxLayout()
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        self.tab.setLayout(tab_layout)

        self._load_printer_preference()

    def set_runtime_dirs(self, exports_dir: Path, print_spool_dir: Path) -> None:
        self._exports_dir = exports_dir
        self._print_spool_dir = print_spool_dir
        self._exports_dir.mkdir(parents=True, exist_ok=True)
        self._print_spool_dir.mkdir(parents=True, exist_ok=True)

    def set_theme_mode(self, theme_mode: str) -> None:
        self._theme_mode = theme_mode if theme_mode in {"light", "dark"} else "dark"

    def _apply_rounded_buttons(self, *buttons: QPushButton) -> None:
        for btn in buttons:
            current = btn.styleSheet() or ""
            btn.setStyleSheet(
                current
                + "\nQPushButton { border-radius: 14px; min-height: 25px; max-height: 25px; padding: 4px 12px; }"
            )

    def refresh_icons(self) -> None:
        self.export_button.setIcon(make_export_icon(20))
        self.export_all_button.setIcon(make_export_all_icon(20))
        self.print_button.setIcon(make_print_icon(20))
        self.print_all_button.setIcon(make_print_all_icon(20))

    # ── Orquestadores ────────────────────────────────────────────────────

    def reload_schedule_source(self) -> None:
        self._load_schedule_rules()
        self._refresh_all()

    def set_schedule_file(self, schedule_path: Path) -> None:
        self._schedule_path = schedule_path
        self._reporte_engine.set_schedule_file(schedule_path)

    def set_report(self, report: AttendanceReport) -> None:
        self.report = report
        self._reporte_engine.set_schedule_file(self._schedule_path)
        self._reporte_engine.set_report(report)
        self._load_schedule_rules()
        csv_teachers = [t for t in report.teachers if self._teacher_exists_in_schedule(t)]
        self._report_teachers_all = self._merge_report_with_schedule_teachers(csv_teachers)
        if not self._report_teachers_all and report.teachers:
            self._report_teachers_all = list(report.teachers)
        self._report_teachers_all.sort(key=lambda t: t.name.lower())
        self._refresh_teacher_selector()
        self._refresh_all()

    def clear_all(self) -> None:
        self.report = None
        self._report_teachers_all = []
        self.teacher_selector.clear()
        self.daily_table.setRowCount(0); self.daily_table.setColumnCount(0)
        self.weekly_table.setRowCount(0); self.weekly_table.setColumnCount(0)
        self.docente_nombre.setText("—")
        self.docente_id.setText("ID: —"); self.docente_depto.setText("Depto: —")
        self.docente_periodo.setText("Periodo: —")
        self.card_horas.setText("00:00"); self.card_asistencia.setText("0%")
        self.card_tardanza.setText("00:00"); self.card_faltas.setText("00:00")
        self.card_extra.setText("00:00"); self.card_extra_tardy.setText("00:00")
        self.card_dias.setText("00:00"); self.card_esperadas.setText("00:00")
        self.card_cumplimiento.setText("0%"); self.card_pendientes.setText("0")
        self.card_bloques.setText("0/0"); self.card_inasistencias.setText("0")
        self.export_button.setEnabled(False)
        self.export_all_button.setEnabled(False)
        self.print_button.setEnabled(False)
        self.print_all_button.setEnabled(False)

    # ── Helpers de horario ───────────────────────────────────────────────

    def _load_schedule_rules(self) -> None:
        self._schedule_aliases_by_dept = {}
        self._teacher_schedule_slots = {}
        self._schedule_teachers = []
        self._day_schedule_aliases_by_dept = {}
        self._day_teacher_schedule_slots = {}
        self._day_teacher_modality_slots = {}
        if self.report and self.report.period_start:
            schedule_dir = self._schedule_path.parent
            for day in self.report.days:
                try:
                    target_date = self.report.period_start.replace(day=day).date()
                except ValueError:
                    continue
                schedule_path = resolve_schedule_for_date(schedule_dir, target_date, self._schedule_path)
                if not schedule_path or not schedule_path.exists():
                    continue
                aliases, slots, modality_weekday = self._extract_rules_from_workbook(schedule_path)
                if aliases:
                    self._day_schedule_aliases_by_dept[day] = aliases
                if slots:
                    self._day_teacher_schedule_slots[day] = slots
                try:
                    weekday_for_day = self.report.period_start.replace(day=day).weekday()
                except ValueError:
                    weekday_for_day = -1
                if weekday_for_day >= 0:
                    day_modality: dict[str, dict[str, set[int]]] = {}
                    for tkey, by_modality in modality_weekday.items():
                        for modality_name, by_weekday in by_modality.items():
                            slot_set = by_weekday.get(weekday_for_day, set())
                            if not slot_set:
                                continue
                            day_modality.setdefault(tkey, {}).setdefault(modality_name, set()).update(slot_set)
                    if day_modality:
                        self._day_teacher_modality_slots[day] = day_modality
                for dept_key, alias_set in aliases.items():
                    self._schedule_aliases_by_dept.setdefault(dept_key, set()).update(alias_set)
                for tkey, by_weekday in slots.items():
                    target = self._teacher_schedule_slots.setdefault(tkey, {})
                    for weekday, slot_set in by_weekday.items():
                        target.setdefault(weekday, set()).update(slot_set)
        elif self._schedule_path.exists():
            aliases, slots, _modality_weekday = self._extract_rules_from_workbook(self._schedule_path)
            self._schedule_aliases_by_dept = aliases
            self._teacher_schedule_slots = slots
        self._schedule_teachers = self._build_schedule_teachers_from_slots(self._teacher_schedule_slots)

    def _build_schedule_teachers_from_slots(self, schedule_slots: dict[str, dict[int, set[int]]]) -> list[TeacherRecord]:
        return build_schedule_teachers_from_slots(schedule_slots)

    def _merge_report_with_schedule_teachers(self, csv_teachers: list[TeacherRecord]) -> list[TeacherRecord]:
        return merge_report_with_schedule_teachers(csv_teachers, self._schedule_teachers)

    def _extract_rules_from_workbook(
        self, xlsx_path: Path
    ) -> tuple[
        dict[str, set[str]],
        dict[str, dict[int, set[int]]],
        dict[str, dict[str, dict[int, set[int]]]],
    ]:
        return get_rules_with_modality(xlsx_path)

    def _teacher_schedule_keys(self, teacher: TeacherRecord) -> list[str]:
        return teacher_schedule_keys(teacher.teacher_id, teacher.name, teacher.department)

    def _modality_slots_for_teacher_day(self, teacher: TeacherRecord, day: int) -> dict[str, set[int]]:
        day_map = self._day_teacher_modality_slots.get(day, {})
        result: dict[str, set[int]] = {}
        for key in self._teacher_schedule_keys(teacher):
            by_mod = day_map.get(key, {})
            for modality_name, slot_set in by_mod.items():
                result.setdefault(modality_name, set()).update(slot_set)
        return result

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

    def _scheduled_slots_for_teacher_weekday(self, teacher: TeacherRecord, weekday: int) -> set[int]:
        return scheduled_slots_for_teacher_weekday(
            teacher.teacher_id, teacher.name, teacher.department,
            self._teacher_schedule_slots, weekday,
        )

    def _aliases_for_day(self, day: int) -> dict[str, set[str]]:
        return self._day_schedule_aliases_by_dept.get(day, self._schedule_aliases_by_dept)

    def _slots_for_day(self, day: int) -> dict[str, dict[int, set[int]]]:
        return self._day_teacher_schedule_slots.get(day, self._teacher_schedule_slots)

    def _mark_for_day(self, teacher: TeacherRecord, day: int) -> str:
        value = teacher.marks.get(day)
        if value is None:
            value = teacher.marks.get(str(day), "")
        return value or ""

    # ── Métricas ─────────────────────────────────────────────────────────

    def _compute_teacher_metrics(self, teacher: TeacherRecord) -> dict:
        return informe_metrics_engine.compute_teacher_metrics(self, teacher)

    def _pending_regularization_count(self, teacher: TeacherRecord, days: list[int]) -> int:
        return informe_metrics_engine.pending_regularization_count(self, teacher, days)

    def _report_column_metrics(self, teacher: TeacherRecord, days: list[int]) -> dict[str, int]:
        return informe_metrics_engine.report_column_metrics(self, teacher, days)

    def _teacher_absence_seconds(self, teacher: TeacherRecord) -> int:
        return informe_attendance_engine.teacher_absence_seconds(self, teacher)

    def _teacher_extra_metrics(self, teacher: TeacherRecord) -> tuple[int, int]:
        return informe_attendance_engine.teacher_extra_metrics(self, teacher)

    def _teacher_early_departure_seconds(self, teacher: TeacherRecord, days: list[int]) -> int:
        return informe_attendance_engine.teacher_early_departure_seconds(self, teacher, days)

    def _teacher_extra_incomplete_seconds(self, teacher: TeacherRecord, days: list[int]) -> int:
        return informe_attendance_engine.teacher_extra_incomplete_seconds(self, teacher, days)

    def _effective_block_seconds(self, block_text: str, slot_idx: int) -> int:
        return self._reporte_engine._effective_block_seconds(block_text, slot_idx)

    def _build_day_slot_values(self, teacher: TeacherRecord) -> list[list[str]]:
        return self._reporte_engine._build_day_slot_values(teacher)

    def _append_slot_value(self, slot_values: list[str], slot_idx: int, text: str) -> None:
        if not (0 <= slot_idx < len(slot_values)):
            return
        value = (text or "").strip()
        if not value:
            return
        current = (slot_values[slot_idx] or "").strip()
        if not current:
            slot_values[slot_idx] = value
            return
        parts = split_cell_blocks(current)
        if value in parts:
            return
        slot_values[slot_idx] = f"{current}\n_____\n{value}"

    def _extract_entry_exit_pairs(self, block_text: str) -> list[tuple[int, int]]:
        return self._reporte_engine._extract_entry_exit_pairs(block_text)

    def _is_pending_regularization_block(self, block_text: str) -> bool:
        return informe_metrics_engine.is_pending_regularization_block(self, block_text)

    def _normalized_event_minutes(self, block_text: str) -> list[int]:
        return self._reporte_engine._normalized_event_minutes(block_text)

    def _teacher_scheduled_tardiness_seconds(self, teacher: TeacherRecord, days: list[int]) -> int:
        return informe_attendance_engine.teacher_scheduled_tardiness_seconds(self, teacher, days)

    def _extra_block_metrics(self, block_text: str) -> tuple[int, int]:
        return self._reporte_engine._extra_block_metrics(block_text)

    def _normalize_extra_block_text(self, block_text: str) -> str:
        return self._reporte_engine._normalize_extra_block_text(block_text)

    def _day_total_seconds(self, teacher: TeacherRecord, day: int) -> int:
        return informe_metrics_engine.day_total_seconds(self, teacher, day)

    # ── UI ───────────────────────────────────────────────────────────────

    def _refresh_teacher_selector(self) -> None:
        current = self.teacher_selector.currentData()
        self.teacher_selector.blockSignals(True)
        self.teacher_selector.clear()
        for teacher in self._report_teachers_all:
            self.teacher_selector.addItem(
                f"{teacher.name} ({teacher.department})",
                teacher,
            )
        idx = self.teacher_selector.findData(current) if current else -1
        self.teacher_selector.setCurrentIndex(idx if idx >= 0 else 0)
        self.teacher_selector.blockSignals(False)
        self.export_button.setEnabled(self.teacher_selector.count() > 0)
        self.export_all_button.setEnabled(self.teacher_selector.count() > 0)
        self.print_button.setEnabled(self.teacher_selector.count() > 0)
        self.print_all_button.setEnabled(self.teacher_selector.count() > 0)

    def _on_teacher_changed(self) -> None:
        self._refresh_all()

    def _refresh_all(self) -> None:
        teacher = self.teacher_selector.currentData()
        if not isinstance(teacher, TeacherRecord) or not self.report:
            self._clear_preview()
            return

        metrics = self._compute_teacher_metrics(teacher)
        if not metrics:
            self._clear_preview()
            return

        month_names = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
            7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
        }
        period_str = ""
        if self.report.period_start:
            m_name = month_names.get(self.report.period_start.month, "")
            period_str = f"{m_name} {self.report.period_start.year}"

        self.docente_nombre.setText(teacher.name.upper())
        self.docente_id.setText(f"ID: {teacher.teacher_id}")
        self.docente_depto.setText(f"Depto: {teacher.department}")
        self.docente_periodo.setText(f"Periodo: {period_str}")

        self.card_horas.setText(format_hm(metrics["total_hours"]))
        self.card_asistencia.setText(f"{metrics['attendance_pct']}%")
        self.card_tardanza.setText(format_hm(metrics["tardiness"]))
        self.card_faltas.setText(format_hm(metrics["absence"]))
        self.card_extra.setText(format_hm(metrics["extra"]))
        self.card_extra_tardy.setText(format_hm(metrics["extra_tardy"]))
        self.card_dias.setText(format_hm(metrics["early_leave"]))
        self.card_esperadas.setText(format_hm(metrics["extra_incomplete"]))
        self.card_cumplimiento.setText(f"{metrics['schedule_compliance_pct']}%")
        self.card_pendientes.setText(str(metrics["pending_regularization"]))
        self.card_bloques.setText(f"{metrics['fulfilled_blocks']}/{metrics['scheduled_blocks']}")
        self.card_inasistencias.setText(str(metrics["absence_blocks"]))

        self._fill_daily_table(teacher)
        self._fill_weekly_table(teacher, metrics)

    def _clear_preview(self) -> None:
        self.docente_nombre.setText("—")
        self.docente_id.setText("ID: —"); self.docente_depto.setText("Depto: —")
        self.docente_periodo.setText("Periodo: —")
        self.card_horas.setText("00:00"); self.card_asistencia.setText("0%")
        self.card_tardanza.setText("00:00"); self.card_faltas.setText("00:00")
        self.card_extra.setText("00:00"); self.card_extra_tardy.setText("00:00")
        self.card_dias.setText("00:00"); self.card_esperadas.setText("00:00")
        self.card_cumplimiento.setText("0%"); self.card_pendientes.setText("0")
        self.card_bloques.setText("0/0"); self.card_inasistencias.setText("0")
        self.daily_table.setRowCount(0); self.daily_table.setColumnCount(0)
        self.weekly_table.setRowCount(0); self.weekly_table.setColumnCount(0)

    def _fill_daily_table(self, teacher: TeacherRecord) -> None:
        return informe_tables_engine.fill_daily_table(self, teacher)

    def _early_departure_minutes_for_block(self, block_text: str, slot_idx: int) -> int:
        return informe_attendance_engine.early_departure_minutes_for_block(self, block_text, slot_idx)

    def _extra_early_departure_minutes_for_block(self, block_text: str) -> int:
        return informe_attendance_engine.extra_early_departure_minutes_for_block(self, block_text)

    def _compact_slot_labels(self, slot_indexes: list[int]) -> str:
        if not slot_indexes:
            return "-"
        ranges: list[tuple[int, int]] = []
        start = slot_indexes[0]
        end = slot_indexes[0]
        for idx in slot_indexes[1:]:
            if idx == end + 1:
                end = idx
            else:
                ranges.append((start, end))
                start = idx
                end = idx
        ranges.append((start, end))

        labels: list[str] = []
        for start_idx, end_idx in ranges:
            start_time = TIME_SLOTS[start_idx].split("-")[0].strip()
            end_time = TIME_SLOTS[end_idx].split("-")[1].strip()
            labels.append(f"{start_time}-{end_time}")
        return ", ".join(labels)

    def _fill_weekly_table(self, teacher: TeacherRecord, metrics: dict) -> None:
        return informe_tables_engine.fill_weekly_table(self, teacher, metrics)

    # Exportar ─────────────────────────────────────────────────────────

    def _available_printer_names(self) -> list[str]:
        names: list[str] = []
        try:
            for printer in QPrinterInfo.availablePrinters():
                name = printer.printerName().strip()
                if name:
                    names.append(name)
        except Exception:
            names = []
        return sorted(set(names), key=str.lower)

    def _load_printer_preference(self) -> None:
        session = load_session(self._data_dir)
        self._preferred_printer = str(session.get("preferred_printer", "")).strip()

    def _save_printer_preference(self, printer_name: str) -> None:
        if not printer_name.strip():
            return
        session = load_session(self._data_dir)
        session["preferred_printer"] = printer_name.strip()
        save_session(self._data_dir, session)
        self._preferred_printer = printer_name.strip()

    def _choose_printer_name(self) -> tuple[str, PrintOptions] | None:
        names = self._available_printer_names()
        if not names:
            QMessageBox.warning(
                self.tab,
                "Impresion",
                "No se detectaron impresoras disponibles en el sistema.",
            )
            return None
        dialog = PrintDialog(names, self.tab, theme_mode=self._theme_mode)
        if self._preferred_printer and self._preferred_printer in names:
            dialog.printer_combo.setCurrentText(self._preferred_printer)
        if dialog.exec() != QDialog.Accepted:
            return None
        selected = dialog.selected_printer()
        if selected:
            self._save_printer_preference(selected)
            self._last_print_options = dialog.selected_options()
            return selected, self._last_print_options
        return None

    def _send_pdf_to_printer(self, pdf_path: Path, printer_name: str, copies: int = 1) -> tuple[bool, str]:
        return self._print_pdf_direct_qt(pdf_path, printer_name, copies)

    def _parse_page_range(self, page_range_text: str, page_count: int) -> list[int]:
        if not page_range_text.strip():
            return list(range(page_count))
        pages: list[int] = []
        for chunk in page_range_text.split(","):
            token = chunk.strip()
            if not token:
                continue
            if "-" in token:
                a_raw, b_raw = token.split("-", maxsplit=1)
                try:
                    a = int(a_raw.strip())
                    b = int(b_raw.strip())
                except ValueError:
                    continue
                start = min(a, b)
                end = max(a, b)
                for n in range(start, end + 1):
                    if 1 <= n <= page_count:
                        pages.append(n - 1)
            else:
                try:
                    n = int(token)
                except ValueError:
                    continue
                if 1 <= n <= page_count:
                    pages.append(n - 1)
        unique: list[int] = []
        seen: set[int] = set()
        for p in pages:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return unique

    def _print_pdf_direct_qt(self, pdf_path: Path, printer_name: str, copies: int) -> tuple[bool, str]:
        try:
            doc = QPdfDocument(self.tab)
            load_error = doc.load(str(pdf_path))
            if load_error != QPdfDocument.Error.None_:
                return False, f"No se pudo cargar PDF (error {load_error})"
            if doc.status() != QPdfDocument.Status.Ready:
                return False, f"PDF no listo para imprimir (estado {doc.status()})"
            page_count = doc.pageCount()
            if page_count <= 0:
                return False, "PDF sin paginas"

            printer = QPrinter(QPrinter.HighResolution)
            printer.setPrinterName(printer_name)
            printer.setOutputFormat(QPrinter.NativeFormat)
            if not printer.isValid():
                return False, "Impresora no valida o no disponible"
            printer.setDocName(pdf_path.stem)
            printer.setFullPage(False)
            printer.setResolution(300)

            selected_options = getattr(self, "_last_print_options", None)
            if isinstance(selected_options, PrintOptions):
                if selected_options.orientation == "Vertical":
                    printer.setPageOrientation(QPageLayout.Portrait)
                elif selected_options.orientation == "Horizontal":
                    printer.setPageOrientation(QPageLayout.Landscape)

                if selected_options.paper_size == "Carta":
                    printer.setPageSize(QPageSize(QPageSize.Letter))
                elif selected_options.paper_size == "Oficio":
                    printer.setPageSize(QPageSize(QPageSize.Legal))
                elif selected_options.paper_size == "A3":
                    printer.setPageSize(QPageSize(QPageSize.A3))
                else:
                    printer.setPageSize(QPageSize(QPageSize.A4))

                if selected_options.color_mode == "Blanco y negro":
                    printer.setColorMode(QPrinter.GrayScale)
                else:
                    printer.setColorMode(QPrinter.Color)

                if selected_options.duplex_mode == "Simple faz":
                    printer.setDuplex(QPrinter.DuplexNone)
                elif selected_options.duplex_mode == "Doble faz (largo)":
                    printer.setDuplex(QPrinter.DuplexLongSide)
                elif selected_options.duplex_mode == "Doble faz (corto)":
                    printer.setDuplex(QPrinter.DuplexShortSide)
                else:
                    printer.setDuplex(QPrinter.DuplexAuto)
                printer.setCollateCopies(bool(selected_options.collate))
            else:
                printer.setCollateCopies(True)

            printer.setCopyCount(max(1, copies))

            page_indexes = list(range(page_count))
            if isinstance(selected_options, PrintOptions):
                if selected_options.page_mode == "Pagina actual":
                    page_indexes = [0]
                elif selected_options.page_mode == "Rango personalizado":
                    page_indexes = self._parse_page_range(selected_options.page_range_text, page_count)
                    if not page_indexes:
                        return False, "Rango de paginas invalido o vacio"

            target_rect = printer.pageRect(QPrinter.DevicePixel)
            if target_rect.width() <= 0 or target_rect.height() <= 0:
                return False, "Area de impresion invalida"

            painter = QPainter()
            if not painter.begin(printer):
                return False, "No se pudo iniciar el motor de impresion"

            render_options = QPdfDocumentRenderOptions()
            try:
                first_page = True
                for page_idx in page_indexes:
                    if not first_page and not printer.newPage():
                        return False, f"No se pudo crear nueva pagina para {page_idx + 1}"
                    painter.fillRect(target_rect, Qt.white)
                    page_pt = doc.pagePointSize(page_idx)
                    dpi = max(72, printer.resolution())
                    render_w = max(1, int(page_pt.width() * dpi / 72.0))
                    render_h = max(1, int(page_pt.height() * dpi / 72.0))
                    image = doc.render(
                        page_idx,
                        QSize(render_w, render_h),
                        render_options,
                    )
                    if image.isNull():
                        return False, f"No se pudo renderizar pagina {page_idx + 1}"
                    # Mantiene proporción para evitar recortes o páginas aparentemente vacías.
                    target_size = QSize(
                        max(1, int(target_rect.width())),
                        max(1, int(target_rect.height())),
                    )
                    scaled = image.scaled(
                        target_size,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                    x = target_rect.x() + (target_rect.width() - scaled.width()) // 2
                    y = target_rect.y() + (target_rect.height() - scaled.height()) // 2
                    painter.drawImage(
                        QRectF(float(x), float(y), float(scaled.width()), float(scaled.height())),
                        scaled,
                        QRectF(0.0, 0.0, float(scaled.width()), float(scaled.height())),
                    )
                    first_page = False
            finally:
                if painter.isActive():
                    painter.end()
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def _build_pdf_for_teacher(self, teacher: TeacherRecord, output_path: Path) -> None:
        if not self.report:
            raise RuntimeError("No hay reporte cargado.")
        metrics = self._compute_teacher_metrics(teacher)
        precomputed = self._build_pdf_precomputed_payload(teacher, metrics)
        schedule_slots_per_weekday: dict[int, set[int]] = {}
        for w in range(7):
            schedule_slots_per_weekday[w] = self._scheduled_slots_for_teacher_weekday(teacher, w)
        generate_teacher_pdf(
            teacher=teacher,
            report=self.report,
            schedule_slots_per_weekday=schedule_slots_per_weekday,
            extra_seconds=metrics["extra"],
            extra_tardy_seconds=metrics["extra_tardy"],
            absence_seconds=metrics["absence"],
            output_path=output_path,
            precomputed=precomputed,
        )

    def _build_pdf_precomputed_payload(self, teacher: TeacherRecord, metrics: dict) -> dict:
        self._fill_daily_table(teacher)
        self._fill_weekly_table(teacher, metrics)

        def _table_snapshot(table) -> tuple[list[str], list[list[str]]]:
            headers: list[str] = []
            rows: list[list[str]] = []
            for c in range(table.columnCount()):
                item = table.horizontalHeaderItem(c)
                headers.append((item.text() if item else "").strip())
            for r in range(table.rowCount()):
                row_vals: list[str] = []
                for c in range(table.columnCount()):
                    item = table.item(r, c)
                    row_vals.append((item.text() if item else "").strip())
                rows.append(row_vals)
            return headers, rows

        daily_headers, daily_rows = _table_snapshot(self.daily_table)
        weekly_headers, weekly_rows = _table_snapshot(self.weekly_table)
        modality_progress = self._build_month_modality_progress(teacher)
        return {
            "metrics": metrics,
            "daily_headers": daily_headers,
            "daily_rows": daily_rows,
            "weekly_headers": weekly_headers,
            "weekly_rows": weekly_rows,
            "modality_progress": modality_progress,
        }

    def _build_month_modality_progress(self, teacher: TeacherRecord) -> list[dict[str, object]]:
        if not self.report or not self.report.period_start:
            return []
        day_slot_values = self._build_day_slot_values(teacher)
        acc: dict[str, tuple[int, int]] = {}
        for day_pos, day in enumerate(self.report.days):
            by_modality = self._modality_slots_for_teacher_day(teacher, day)
            slot_values = day_slot_values[day_pos] if day_pos < len(day_slot_values) else [""] * len(TIME_SLOTS)
            for modality_name, slot_indices in by_modality.items():
                expected = 0
                attended = 0
                for idx in sorted(slot_indices):
                    expected += slot_duration_seconds(idx)
                    if 0 <= idx < len(slot_values):
                        attended += self._effective_block_seconds(slot_values[idx], idx)
                prev_expected, prev_attended = acc.get(modality_name, (0, 0))
                acc[modality_name] = (prev_expected + expected, prev_attended + attended)
        out: list[dict[str, object]] = []
        for modality_name, (expected, attended) in sorted(acc.items(), key=lambda x: x[0].lower()):
            pct = min(int((attended / max(expected, 1)) * 100), 100) if expected > 0 else 0
            out.append({
                "name": modality_name,
                "expected": expected,
                "attended": attended,
                "pct": pct,
            })
        return out

    def _on_export_clicked(self) -> None:
        teacher = self.teacher_selector.currentData()
        if not isinstance(teacher, TeacherRecord) or not self.report:
            QMessageBox.warning(self.tab, "Exportar PDF", "Seleccione un docente primero.")
            return

        metrics = self._compute_teacher_metrics(teacher)

        schedule_slots_per_weekday: dict[int, set[int]] = {}
        for w in range(7):
            schedule_slots_per_weekday[w] = self._scheduled_slots_for_teacher_weekday(teacher, w)

        suggested_name = f"Informe_{teacher.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        session = load_session(self._data_dir)
        start_dir = session.get(self._SESSION_KEY_EXPORT_PDF_DIR, str(Path.home() / "Documents"))
        file_path, _ = QFileDialog.getSaveFileName(
            self.tab,
            "Guardar Informe PDF",
            str(Path(start_dir) / suggested_name),
            "PDF (*.pdf)",
        )
        if not file_path:
            return
        session[self._SESSION_KEY_EXPORT_PDF_DIR] = str(Path(file_path).parent)
        save_session(self._data_dir, session)

        self.export_button.setEnabled(False)
        self.export_button.setText("Generando PDF...")

        try:
            generate_teacher_pdf(
                teacher=teacher,
                report=self.report,
                schedule_slots_per_weekday=schedule_slots_per_weekday,
                extra_seconds=metrics["extra"],
                extra_tardy_seconds=metrics["extra_tardy"],
                absence_seconds=metrics["absence"],
                output_path=Path(file_path),
                precomputed=self._build_pdf_precomputed_payload(teacher, metrics),
            )
            QMessageBox.information(
                self.tab,
                "PDF Generado",
                f"Informe exportado exitosamente:\n{file_path}",
            )
        except Exception as exc:
            logger.error("Error al generar PDF: %s", exc)
            QMessageBox.critical(self.tab, "Error", f"No se pudo generar el PDF:\n{exc}")
        finally:
            self.export_button.setEnabled(True)
            self.export_button.setText("Exportar PDF")
            self.export_all_button.setEnabled(self.teacher_selector.count() > 0)
            self.print_button.setEnabled(self.teacher_selector.count() > 0)
            self.print_all_button.setEnabled(self.teacher_selector.count() > 0)

    def _on_export_all_clicked(self) -> None:
        if not self.report:
            QMessageBox.warning(self.tab, "Exportar PDFs", "No hay reporte cargado.")
            return

        scheduled_teachers = list(self._report_teachers_all)
        if not scheduled_teachers:
            QMessageBox.warning(
                self.tab,
                "Exportar PDFs",
                "No se encontraron docentes del reporte que figuren en el horario cargado.",
            )
            return

        session = load_session(self._data_dir)
        start_dir = session.get(self._SESSION_KEY_EXPORT_ALL_DIR, str(self._exports_dir))
        output_dir_str = QFileDialog.getExistingDirectory(
            self.tab,
            "Seleccionar carpeta destino para informes",
            start_dir if start_dir else str(Path.home() / "Documents"),
        )
        if not output_dir_str:
            return
        output_dir = Path(output_dir_str)
        session[self._SESSION_KEY_EXPORT_ALL_DIR] = str(output_dir)
        save_session(self._data_dir, session)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.export_button.setEnabled(False)
        self.export_all_button.setEnabled(False)
        self.print_button.setEnabled(False)
        self.print_all_button.setEnabled(False)
        self.export_all_button.setText("Exportando...")

        exported = 0
        failed: list[str] = []
        try:
            for teacher in sorted(scheduled_teachers, key=lambda t: t.name.lower()):
                metrics = self._compute_teacher_metrics(teacher)
                schedule_slots_per_weekday: dict[int, set[int]] = {}
                for w in range(7):
                    schedule_slots_per_weekday[w] = self._scheduled_slots_for_teacher_weekday(teacher, w)

                safe_name = re.sub(r"[^A-Za-z0-9_\\-]+", "_", teacher.name.replace(" ", "_")).strip("_") or "Docente"
                out_path = output_dir / f"Informe_{safe_name}_{timestamp}.pdf"

                try:
                    generate_teacher_pdf(
                        teacher=teacher,
                        report=self.report,
                        schedule_slots_per_weekday=schedule_slots_per_weekday,
                        extra_seconds=metrics["extra"],
                        extra_tardy_seconds=metrics["extra_tardy"],
                        absence_seconds=metrics["absence"],
                        output_path=out_path,
                        precomputed=self._build_pdf_precomputed_payload(teacher, metrics),
                    )
                    exported += 1
                except Exception as exc:
                    logger.error("Error exportando PDF de '%s': %s", teacher.name, exc)
                    failed.append(f"{teacher.name}: {exc}")
        finally:
            self.export_button.setEnabled(self.teacher_selector.count() > 0)
            self.export_all_button.setEnabled(self.teacher_selector.count() > 0)
            self.print_button.setEnabled(self.teacher_selector.count() > 0)
            self.print_all_button.setEnabled(self.teacher_selector.count() > 0)
            self.export_all_button.setText("Exportar Todos")

        if failed:
            details = "\n".join(failed[:8])
            suffix = "\n..." if len(failed) > 8 else ""
            QMessageBox.warning(
                self.tab,
                "Exportacion completada con errores",
                (
                    f"Exportados: {exported}\n"
                    f"Fallidos: {len(failed)}\n\n"
                    f"{details}{suffix}"
                ),
            )
        else:
            QMessageBox.information(
                self.tab,
                "Exportacion completada",
                f"Se exportaron {exported} informes en:\n{output_dir}",
            )

    def _on_print_clicked(self) -> None:
        teacher = self.teacher_selector.currentData()
        if not isinstance(teacher, TeacherRecord) or not self.report:
            QMessageBox.warning(self.tab, "Imprimir", "Seleccione un docente primero.")
            return

        selection = self._choose_printer_name()
        if not selection:
            return
        printer_name, options = selection

        enabled = self.teacher_selector.count() > 0
        self.print_button.setEnabled(False)
        self.print_button.setText("Imprimiendo...")
        self.export_button.setEnabled(False)
        self.export_all_button.setEnabled(False)
        self.print_all_button.setEnabled(False)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r"[^A-Za-z0-9_\\-]+", "_", teacher.name.replace(" ", "_")).strip("_") or "Docente"
        spool_dir = self._print_spool_dir
        spool_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = spool_dir / f"Imprimir_{safe_name}_{timestamp}.pdf"

        try:
            self._build_pdf_for_teacher(teacher, pdf_path)
            ok, err = self._send_pdf_to_printer(pdf_path, printer_name, options.copies)
            if not ok:
                raise RuntimeError(err or "No se pudo enviar a la impresora.")
            QMessageBox.information(self.tab, "Impresion enviada", f"Documento enviado a:\n{printer_name}")
        except Exception as exc:
            logger.error("Error al imprimir PDF: %s", exc)
            QMessageBox.critical(self.tab, "Error", f"No se pudo imprimir:\n{exc}")
        finally:
            self.print_button.setEnabled(enabled)
            self.print_button.setText("Imprimir")
            self.export_button.setEnabled(enabled)
            self.export_all_button.setEnabled(enabled)
            self.print_all_button.setEnabled(enabled)

    def _on_print_all_clicked(self) -> None:
        if not self.report:
            QMessageBox.warning(self.tab, "Imprimir Todos", "No hay reporte cargado.")
            return

        scheduled_teachers = list(self._report_teachers_all)
        if not scheduled_teachers:
            QMessageBox.warning(
                self.tab,
                "Imprimir Todos",
                "No se encontraron docentes del reporte que figuren en el horario cargado.",
            )
            return

        selection = self._choose_printer_name()
        if not selection:
            return
        printer_name, options = selection

        enabled = self.teacher_selector.count() > 0
        self.print_all_button.setEnabled(False)
        self.print_all_button.setText("Imprimiendo...")
        self.print_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.export_all_button.setEnabled(False)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        spool_dir = self._print_spool_dir / f"Lote_{timestamp}"
        spool_dir.mkdir(parents=True, exist_ok=True)

        sent = 0
        failed: list[str] = []
        try:
            for teacher in sorted(scheduled_teachers, key=lambda t: t.name.lower()):
                safe_name = re.sub(r"[^A-Za-z0-9_\\-]+", "_", teacher.name.replace(" ", "_")).strip("_") or "Docente"
                pdf_path = spool_dir / f"Imprimir_{safe_name}_{timestamp}.pdf"
                try:
                    self._build_pdf_for_teacher(teacher, pdf_path)
                    ok, err = self._send_pdf_to_printer(pdf_path, printer_name, options.copies)
                    if not ok:
                        raise RuntimeError(err or "Error enviando a impresora")
                    sent += 1
                except Exception as exc:
                    logger.error("Error imprimiendo '%s': %s", teacher.name, exc)
                    failed.append(f"{teacher.name}: {exc}")
        finally:
            self.print_all_button.setEnabled(enabled)
            self.print_all_button.setText("Imprimir Todos")
            self.print_button.setEnabled(enabled)
            self.export_button.setEnabled(enabled)
            self.export_all_button.setEnabled(enabled)

        if failed:
            details = "\n".join(failed[:8])
            suffix = "\n..." if len(failed) > 8 else ""
            QMessageBox.warning(
                self.tab,
                "Impresion completada con errores",
                f"Enviados: {sent}\nFallidos: {len(failed)}\n\n{details}{suffix}",
            )
        else:
            QMessageBox.information(
                self.tab,
                "Impresion completada",
                f"Se enviaron {sent} informes a:\n{printer_name}",
            )
