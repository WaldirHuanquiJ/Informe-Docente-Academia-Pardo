from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPalette, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)

from app.models import AttendanceReport, TeacherRecord
from app.services.horario_excel import load_horarios_workbook
from app.services.schedule_rules_cache import get_basic_rules, get_rules_with_modality
from app.services.schedule_versions import resolve_schedule_for_date
from app.ui.icon_factory import make_import_icon, make_clear_icon
from app.services.logging_config import get_logger
from app.services.session_store import load_session, save_session
from app.services.labor_calendar import load_calendar, month_key
from app.services.schedule_utils import (
    HEADER_NAMES,
    TIME_SLOTS,
    SLOT_START_MINUTES,
    extract_course_alias_pairs,
    extract_course_and_alias,
    extract_schedule_blocks,
    extract_schedule_blocks_with_continuity,
    first_time_minutes,
    format_hm,
    norm,
    norm_name,
    scheduled_slots_for_teacher_weekday,
    slot_bounds_minutes,
    slot_index_for_block,
    slot_index_for_label,
    slot_start_minutes,
    slot_duration_seconds,
    slot_indexes_for_label,
    teacher_exists_in_schedule,
    teacher_schedule_keys,
)
from app.services.time_rules import (
    compute_seconds_from_mark_text,
    split_cell_blocks,
)
from app.services.attendance_engine import (
    DEFAULT_POLICY,
    extract_entry_exit_pairs,
    extract_single_entry_minutes,
    extract_trailing_unpaired_entry_minutes,
    extra_block_metrics,
    extra_planned_window,
    normalize_extra_block_text,
    normalized_event_minutes,
)
from app.services.day_slot_engine import build_day_slot_values

logger = get_logger(__name__)


class AttendanceCellDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._column_highlights: dict[int, QColor] = {}

    def set_column_highlights(self, highlights: dict[int, QColor]) -> None:
        self._column_highlights = dict(highlights)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # type: ignore[override]
        col_color = self._column_highlights.get(index.column())
        if col_color is not None:
            painter.save()
            painter.fillRect(option.rect, QBrush(col_color))
            painter.restore()
            text = str(index.data(Qt.DisplayRole) or "")
            painter.save()
            painter.setPen(option.palette.color(QPalette.Text))
            painter.setFont(option.font)
            draw_rect = option.rect.adjusted(6, 0, -6, 0)
            painter.drawText(draw_rect, int(Qt.AlignCenter | Qt.AlignVCenter), text)
            painter.restore()
        else:
            super().paint(painter, option, index)
        if bool(index.data(Qt.UserRole)):
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, False)
            is_light = option.palette.color(QPalette.Base).lightness() > 170
            status = (index.data(Qt.UserRole + 1) or "").upper()
            if status == "FALTA":
                border_color = QColor("#c62828") if is_light else QColor(255, 95, 95)
            elif status == "TARDANZA":
                border_color = QColor("#1565c0") if is_light else QColor(90, 180, 255)
            elif status == "PENDIENTE":
                border_color = QColor("#f9a825") if is_light else QColor(255, 220, 120)
            else:
                border_color = QColor("#16a34a") if is_light else QColor(230, 255, 0)
            pen = QPen(border_color)
            pen.setWidth(2)
            painter.setPen(pen)
            rect = option.rect.adjusted(1, 1, -1, -1)
            painter.drawRect(rect)
            painter.restore()


class ReporteView:
    MIN_VALID_ATTENDANCE_MINUTES = DEFAULT_POLICY.min_valid_attendance_minutes
    EARLY_PUNCTUAL_WINDOW_MINUTES = 90
    DUPLICATE_MARK_WINDOW_MINUTES = DEFAULT_POLICY.duplicate_mark_window_minutes
    EXTRA_EARLY_ROUNDING_MINUTES = DEFAULT_POLICY.extra_early_rounding_minutes
    EXTRA_BLOCK_MINUTES = DEFAULT_POLICY.extra_block_minutes
    REPORT_ROWS_PER_TEACHER = 7
    _SESSION_KEY_IMPORT_DIR = "last_import_reporte_dir"

    def __init__(self, data_dir: Path) -> None:
        self.tab = QWidget()
        self.base_headers = ["ID", "Nombre", "Departamento"]
        self.filtered_teachers: list[TeacherRecord] = []
        self.report: AttendanceReport | None = None
        self._data_dir = data_dir
        self._schedule_path = self._data_dir / "HORARIOS.xlsx"
        self.on_import_xls: callable | None = None
        self.on_clear: callable | None = None
        self._dept_weekdays: dict[str, set[int]] = {}
        self._dept_day_start_minutes: dict[str, dict[int, list[int]]] = {}
        self._schedule_aliases_by_dept: dict[str, set[str]] = {}
        self._schedule_aliases_global: set[str] = set()
        self._teacher_schedule_slots: dict[str, dict[int, set[int]]] = {}
        self._day_schedule_aliases_by_dept: dict[int, dict[str, set[str]]] = {}
        self._day_teacher_schedule_slots: dict[int, dict[str, dict[int, set[int]]]] = {}
        self._day_teacher_modality_slots: dict[int, dict[str, dict[str, set[int]]]] = {}
        self._day_schedule_name: dict[int, str] = {}
        self._schedule_teachers: list[TeacherRecord] = []
        self._report_teachers_all: list[TeacherRecord] = []
        self._theme_mode: str = "dark"
        self._labor_calendar = load_calendar(self._data_dir)
        self._filter_timer = QTimer(self.tab)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(140)
        self._filter_timer.timeout.connect(self.refresh_table)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Buscar por nombre")
        self.search_box.setMaximumWidth(320)

        self.department_filter = QComboBox()
        self.department_filter.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.department_filter.setMinimumContentsLength(22)
        self.import_xls_button = QPushButton("Importar XLS/CSV biometrico")
        self.import_xls_button.setMaximumWidth(220)
        self.import_xls_button.clicked.connect(self._on_import_xls_clicked)
        self.clear_button = QPushButton("Limpiar")
        self.clear_button.setMaximumWidth(120)
        self.clear_button.clicked.connect(self._on_clear_clicked)
        import_icon = make_import_icon(20)
        clear_icon = make_clear_icon(20)
        self.import_xls_button.setIcon(import_icon)
        self.import_xls_button.setObjectName("actionImport")
        self.clear_button.setIcon(clear_icon)
        self.clear_button.setObjectName("actionClear")
        self.import_xls_button.setIconSize(QSize(20, 20))
        self.clear_button.setIconSize(QSize(20, 20))
        self._apply_rounded_buttons(
            self.import_xls_button,
            self.clear_button,
        )

        self.info_label = QLabel()
        self.info_label.setObjectName("infoLabel")
        self.info_label.setWordWrap(True)
        self.status_host = QWidget()
        self.status_host.setObjectName("HorarioStatusHost")
        self.status_layout = QHBoxLayout()
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_layout.setSpacing(6)
        self.status_host.setLayout(self.status_layout)

        self.table = QTableWidget()
        self.table.setObjectName("ReporteTable")
        self._delegate = AttendanceCellDelegate(self.table)
        self.table.setItemDelegate(self._delegate)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setShowGrid(True)
        self.table.setSortingEnabled(False)
        self.table.setStyleSheet(
            "QTableWidget::item { padding: 7px 10px; border-bottom: 1px solid rgba(120,120,120,0.22); }"
        )

        top_controls = QHBoxLayout()
        top_controls.addWidget(self.search_box)
        top_controls.addWidget(self.department_filter)
        top_controls.addWidget(self.import_xls_button)
        top_controls.addWidget(self.clear_button)
        top_controls.addStretch(1)

        layout = QVBoxLayout()
        layout.addLayout(top_controls)
        layout.addWidget(self.status_host)
        layout.addWidget(self.table)
        self.tab.setLayout(layout)

        self.search_box.textChanged.connect(self._schedule_refresh_table)
        self.department_filter.currentIndexChanged.connect(self._schedule_refresh_table)

    def set_theme_mode(self, theme_mode: str) -> None:
        normalized = (theme_mode or "").strip().lower()
        new_mode = normalized if normalized in {"light", "dark"} else "dark"
        if new_mode == self._theme_mode:
            return
        self._theme_mode = new_mode
        self._apply_theme_to_current_table()

    def _schedule_refresh_table(self) -> None:
        self._filter_timer.start()

    def _theme_column_colors(self) -> tuple[QColor, QColor, QColor]:
        is_light = self._is_light_theme_active()
        indicated_bg = QColor("#EAF7EE") if is_light else QColor("#132A20")
        extra_bg = QColor("#FFF2E6") if is_light else QColor("#2F2114")
        faltas_bg = QColor("#FDEBEC") if is_light else QColor("#31141A")
        return indicated_bg, extra_bg, faltas_bg

    def _apply_theme_to_current_table(self) -> None:
        if self.table.columnCount() < 8:
            return
        indicated_bg, extra_bg, faltas_bg = self._theme_column_colors()
        total_asistencia_col = self.table.columnCount() - 8
        total_tardanza_col = self.table.columnCount() - 7
        salida_anticipada_col = self.table.columnCount() - 6
        horas_extra_col = self.table.columnCount() - 5
        tardanza_extra_col = self.table.columnCount() - 4
        extra_incompleta_col = self.table.columnCount() - 3
        faltas_col = self.table.columnCount() - 2
        horas_deuda_col = self.table.columnCount() - 1

        for c in (total_asistencia_col, total_tardanza_col, salida_anticipada_col):
            h = self.table.horizontalHeaderItem(c)
            if h is not None:
                h.setBackground(indicated_bg)
        for c in (horas_extra_col, tardanza_extra_col, extra_incompleta_col):
            h = self.table.horizontalHeaderItem(c)
            if h is not None:
                h.setBackground(extra_bg)
        for c in (faltas_col, horas_deuda_col):
            h = self.table.horizontalHeaderItem(c)
            if h is not None:
                h.setBackground(faltas_bg)

        self._delegate.set_column_highlights(
            {
                total_asistencia_col: indicated_bg,
                total_tardanza_col: indicated_bg,
                salida_anticipada_col: indicated_bg,
                horas_extra_col: extra_bg,
                tardanza_extra_col: extra_bg,
                extra_incompleta_col: extra_bg,
                faltas_col: faltas_bg,
                horas_deuda_col: faltas_bg,
            }
        )

        for row_idx in range(self.table.rowCount()):
            for col_idx in (total_asistencia_col, total_tardanza_col, salida_anticipada_col):
                item = self.table.item(row_idx, col_idx)
                if item is not None:
                    item.setBackground(indicated_bg)
            for col_idx in (horas_extra_col, tardanza_extra_col, extra_incompleta_col):
                item = self.table.item(row_idx, col_idx)
                if item is not None:
                    item.setBackground(extra_bg)
            for c in (faltas_col, horas_deuda_col):
                item_f = self.table.item(row_idx, c)
                if item_f is not None:
                    item_f.setBackground(faltas_bg)

        self.table.viewport().update()

    def _apply_rounded_buttons(self, *buttons: QPushButton) -> None:
        for btn in buttons:
            current = btn.styleSheet() or ""
            btn.setStyleSheet(
                current
                + "\nQPushButton { border-radius: 14px; min-height: 25px; max-height: 25px; padding: 4px 12px; }"
            )

    def refresh_icons(self) -> None:
        self.import_xls_button.setIcon(make_import_icon(20))
        self.clear_button.setIcon(make_clear_icon(20))

    def _status_colors(self) -> tuple[QColor, QColor, QColor]:
        app = QApplication.instance()
        is_light = True
        if app is not None:
            is_light = app.palette().window().color().lightness() > 160
        if is_light:
            return (QColor("#c62828"), QColor("#0f9d58"), QColor("#1565c0"))
        return (QColor(255, 95, 95), QColor(0, 220, 100), QColor(90, 180, 255))

    def reload_schedule_source(self) -> None:
        self._load_schedule_rules()
        if self.report:
            self._report_teachers_all = self._merge_report_with_schedule_teachers(self.report.teachers)
            self.refresh_department_filter()
            self.refresh_table()

    def _on_import_xls_clicked(self) -> None:
        session = load_session(self._data_dir)
        start_dir = session.get(self._SESSION_KEY_IMPORT_DIR, str(Path.home() / "Documents"))
        file_path, _ = QFileDialog.getOpenFileName(
            self.tab,
            "Seleccionar archivo biometrico",
            start_dir,
            "Biometrico (*.xls *.csv);;Excel 97-2003 (*.xls);;CSV (*.csv);;Todos los archivos (*.*)",
        )
        if not file_path:
            return
        selected = Path(file_path)
        session[self._SESSION_KEY_IMPORT_DIR] = str(selected.parent)
        save_session(self._data_dir, session)
        if callable(self.on_import_xls):
            self.on_import_xls(selected)

    def _on_clear_clicked(self) -> None:
        if callable(self.on_clear):
            self.on_clear()

    def set_report(self, report: AttendanceReport) -> None:
        self.report = report
        self._labor_calendar = load_calendar(self._data_dir)
        self._load_schedule_rules()
        self._report_teachers_all = self._merge_report_with_schedule_teachers(report.teachers)
        ok, msg = self._compatibility_status(report)
        badge_text = "COMPATIBLE" if ok else "NO COMPATIBLE"
        self._set_status_chips(
            [
                self._period_title(),
                f"Periodo: {report.period}",
                f"Actualizado: {report.generated_date}",
                f"Estado: {badge_text}",
                msg,
            ]
        )
        self.refresh_department_filter()
        self.refresh_table()

    def refresh_department_filter(self) -> None:
        if not self.report:
            return
        current_value = self.department_filter.currentText()
        departments = sorted({teacher.department for teacher in self._report_teachers_all})
        self.department_filter.blockSignals(True)
        self.department_filter.clear()
        self.department_filter.addItem("Todos los departamentos")
        self.department_filter.addItems(departments)
        idx = self.department_filter.findText(current_value)
        self.department_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.department_filter.blockSignals(False)

    def refresh_table(self) -> None:
        if not self.report:
            return
        self._labor_calendar = load_calendar(self._data_dir)
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        color_falta, color_tardanza, color_puntual = self._status_colors()
        query_name = self.search_box.text().strip().lower()
        selected_department = self.department_filter.currentText()

        self.filtered_teachers = []
        for teacher in self._report_teachers_all:
            if query_name and query_name not in teacher.name.lower():
                continue
            if selected_department != "Todos los departamentos" and teacher.department != selected_department:
                continue
            self.filtered_teachers.append(teacher)

        day_headers = [self._day_header_label(day) for day in self.report.days]
        headers = self.base_headers + ["Bloque"] + day_headers + [
            "Total Asistencia",
            "Total Tardanza",
            "Salida anticipada",
            "Horas Extra",
            "Tardanza Extra",
            "Extra incompleta",
            "Faltas",
            "Horas deuda",
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        time_font = QFont("Consolas", 10)
        time_font.setStyleHint(QFont.Monospace)

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 120)
        for idx in range(len(self.base_headers) + 1, len(headers)):
            self.table.setColumnWidth(idx, 72)
        self.table.setColumnWidth(len(headers) - 8, 130)  # Total Asistencia
        self.table.setColumnWidth(len(headers) - 7, 120)  # Total Tardanza
        self.table.setColumnWidth(len(headers) - 6, 140)  # Salida anticipada
        self.table.setColumnWidth(len(headers) - 5, 120)  # Horas Extra
        self.table.setColumnWidth(len(headers) - 4, 120)  # Tardanza Extra
        self.table.setColumnWidth(len(headers) - 3, 130)  # Extra incompleta
        self.table.setColumnWidth(len(headers) - 2, 90)   # Faltas
        self.table.setColumnWidth(len(headers) - 1, 110)  # Horas deuda

        total_asistencia_col = len(headers) - 8
        total_tardanza_col = len(headers) - 7
        salida_anticipada_col = len(headers) - 6
        horas_extra_col = len(headers) - 5
        tardanza_extra_col = len(headers) - 4
        extra_incompleta_col = len(headers) - 3
        faltas_col = len(headers) - 2
        horas_deuda_col = len(headers) - 1

        indicated_bg, extra_bg, faltas_bg = self._theme_column_colors()

        for c in (total_asistencia_col, total_tardanza_col, salida_anticipada_col):
            h = self.table.horizontalHeaderItem(c)
            if h is not None:
                h.setBackground(indicated_bg)
        for c in (horas_extra_col, tardanza_extra_col, extra_incompleta_col):
            h = self.table.horizontalHeaderItem(c)
            if h is not None:
                h.setBackground(extra_bg)
        for c in (faltas_col, horas_deuda_col):
            h = self.table.horizontalHeaderItem(c)
            if h is not None:
                h.setBackground(faltas_bg)

        self._delegate.set_column_highlights(
            {
                total_asistencia_col: indicated_bg,
                total_tardanza_col: indicated_bg,
                salida_anticipada_col: indicated_bg,
                horas_extra_col: extra_bg,
                tardanza_extra_col: extra_bg,
                extra_incompleta_col: extra_bg,
                faltas_col: faltas_bg,
                horas_deuda_col: faltas_bg,
            }
        )

        teacher_metrics: dict[str, tuple[int, int, int, int, int, int, int, int]] = {}
        expanded_rows: list[tuple[TeacherRecord, int, list[list[str]]]] = []
        for teacher in self.filtered_teachers:
            day_slot_values = self._build_day_slot_values(teacher)
            teacher_total_seconds = 0
            for day_pos, day in enumerate(self.report.days):
                for slot_idx in range(self.REPORT_ROWS_PER_TEACHER):
                    if self._is_non_working_day(day):
                        continue
                    block_text = day_slot_values[day_pos][slot_idx]
                    if self._is_scheduled_block(teacher, day, slot_idx):
                        teacher_total_seconds += self._effective_block_seconds(block_text, slot_idx)
                    else:
                        teacher_total_seconds += compute_seconds_from_mark_text(block_text)
            teacher_tardiness_seconds = 0
            for day_pos, day in enumerate(self.report.days):
                for slot_idx in range(self.REPORT_ROWS_PER_TEACHER):
                    if not self._is_scheduled_block(teacher, day, slot_idx):
                        continue
                    cell_value = day_slot_values[day_pos][slot_idx]
                    if self._is_pending_regularization_block(cell_value):
                        continue
                    teacher_tardiness_seconds += self._compute_scheduled_tardiness_seconds(
                        teacher=teacher,
                        day=day,
                        block_idx=slot_idx,
                        cell_value=cell_value,
                    )
            teacher_extra_seconds, teacher_extra_tardy_seconds = self._compute_teacher_extra_metrics(
                teacher, day_slot_values
            )
            teacher_early_departure_minutes_scheduled = self._compute_teacher_early_departure_minutes(teacher, day_slot_values)
            teacher_early_departure_minutes_extra = self._compute_teacher_extra_early_departure_minutes(teacher, day_slot_values)
            teacher_faltas_seconds = self._count_teacher_faltas_seconds(teacher)
            teacher_suspended_seconds = self._count_teacher_debt_seconds(teacher)
            teacher_non_working_seconds = self._count_teacher_non_working_mark_seconds(teacher)
            teacher_debt_seconds = max(
                teacher_faltas_seconds
                + teacher_tardiness_seconds
                + (teacher_early_departure_minutes_scheduled * 60)
                + teacher_suspended_seconds
                + teacher_non_working_seconds
                - teacher_extra_seconds,
                0,
            )
            tkey = f"{teacher.teacher_id}|{teacher.name}|{teacher.department}"
            teacher_metrics[tkey] = (
                teacher_total_seconds,
                teacher_tardiness_seconds,
                teacher_extra_seconds,
                teacher_extra_tardy_seconds,
                teacher_early_departure_minutes_scheduled,
                teacher_early_departure_minutes_extra,
                teacher_faltas_seconds,
                teacher_debt_seconds,
            )
            for block_idx in range(self.REPORT_ROWS_PER_TEACHER):
                expanded_rows.append((teacher, block_idx, day_slot_values))

        self.table.setRowCount(len(expanded_rows))

        for row_idx, (teacher, block_idx, day_slot_values) in enumerate(expanded_rows):
            tkey = f"{teacher.teacher_id}|{teacher.name}|{teacher.department}"
            (
                teacher_total_seconds,
                teacher_tardiness_seconds,
                teacher_extra_seconds,
                teacher_extra_tardy_seconds,
                teacher_early_departure_minutes_scheduled,
                teacher_early_departure_minutes_extra,
                teacher_faltas_seconds,
                teacher_debt_seconds,
            ) = teacher_metrics[tkey]
            values = [teacher.teacher_id, teacher.name, teacher.department]
            values.append(TIME_SLOTS[block_idx])
            for day_pos, day in enumerate(self.report.days):
                values.append(day_slot_values[day_pos][block_idx])
            values.append(format_hm(teacher_total_seconds) if block_idx == 0 else "")
            values.append(format_hm(teacher_tardiness_seconds) if block_idx == 0 else "")
            values.append(format_hm(teacher_early_departure_minutes_scheduled * 60) if block_idx == 0 else "")
            values.append(format_hm(teacher_extra_seconds) if block_idx == 0 else "")
            values.append(format_hm(teacher_extra_tardy_seconds) if block_idx == 0 else "")
            values.append(format_hm(teacher_early_departure_minutes_extra * 60) if block_idx == 0 else "")
            values.append(format_hm(teacher_faltas_seconds) if block_idx == 0 else "")
            values.append(format_hm(teacher_debt_seconds) if block_idx == 0 else "")

            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col_idx < len(self.base_headers):
                    if block_idx > 0:
                        item.setText("")
                elif col_idx == len(self.base_headers):
                    item.setTextAlignment(Qt.AlignCenter)
                    block_font = QFont("Segoe UI", 9)
                    block_font.setBold(True)
                    item.setFont(block_font)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                    day_start_col = len(self.base_headers) + 1
                    day_end_col = day_start_col + len(self.report.days)
                    if col_idx < day_end_col:
                        item.setFont(time_font)
                        day_pos = col_idx - day_start_col
                        day = self.report.days[day_pos]
                        is_scheduled_block = self._is_scheduled_block(teacher, day, block_idx)
                        tardy_seconds = self._compute_scheduled_tardiness_seconds(
                            teacher=teacher,
                            day=day,
                            block_idx=block_idx,
                            cell_value=value,
                        )
                        if is_scheduled_block:
                            item.setData(Qt.UserRole, True)
                        is_suspended_block = is_scheduled_block and self._is_suspended_block(teacher, day, block_idx)
                        is_non_working_day = self._is_non_working_day(day)

                        if is_non_working_day and value.strip():
                            item.setForeground(color_falta)
                            item.setData(Qt.UserRole, True)
                            item.setData(Qt.UserRole + 1, "FALTA")
                            item.setBackground(QColor(255, 240, 240))
                            item.setToolTip("Dia no laborable: estas horas se cuentan solo en Horas deuda")
                        elif is_non_working_day and is_scheduled_block:
                            item.setText("")
                            item.setData(Qt.UserRole, False)
                            item.setData(Qt.UserRole + 1, "")
                            item.setBackground(QColor(229, 231, 235))
                            item.setToolTip("Dia no laborable: bloque oculto y no cuenta como falta")
                        elif is_scheduled_block and is_suspended_block:
                            item.setText("")
                            item.setData(Qt.UserRole, False)
                            item.setData(Qt.UserRole + 1, "")
                            item.setBackground(QColor(229, 231, 235))
                            item.setToolTip("Bloque suspendido: no penaliza y no se grafica")
                        elif value.strip():
                            block_seconds = self._effective_block_seconds(value, block_idx) if is_scheduled_block else compute_seconds_from_mark_text(value)
                            if is_scheduled_block and self._is_pending_regularization_block(value):
                                item.setForeground(QColor("#b26a00"))
                                item.setData(Qt.UserRole + 1, "PENDIENTE")
                                item.setBackground(QColor(255, 248, 225))
                                item.setToolTip("Falta (pendiente de regularizacion): falta registrar salida")
                            elif is_scheduled_block and self._is_excessively_early_entry(value, block_idx):
                                item.setForeground(QColor("#8a6d1f"))
                                item.setData(Qt.UserRole + 1, "PENDIENTE")
                                item.setBackground(QColor(255, 248, 225))
                                item.setToolTip("Entrada atipica: mas de 1h30 antes del horario")
                            elif is_scheduled_block and block_seconds < self._min_valid_seconds_for_scheduled_block(block_idx):
                                item.setForeground(color_falta)
                                item.setData(Qt.UserRole + 1, "FALTA")
                                item.setBackground(QColor(255, 240, 240))
                                item.setToolTip("Falta: registro menor a 1 hora en bloque programado")
                            elif is_scheduled_block and tardy_seconds > 0:
                                item.setForeground(color_tardanza)
                                item.setData(Qt.UserRole + 1, "TARDANZA")
                                item.setBackground(QColor(235, 245, 255))
                                item.setToolTip(f"Tardanza detectada: {value}")
                            else:
                                item.setForeground(color_puntual)
                                item.setData(Qt.UserRole + 1, "PUNTUAL")
                                item.setBackground(QColor(236, 252, 242))
                                item.setToolTip(f"Puntual: {value}")
                        elif is_scheduled_block:
                            item.setForeground(color_falta)
                            item.setData(Qt.UserRole + 1, "FALTA")
                            item.setBackground(QColor(255, 240, 240))
                            item.setToolTip("Falta: segun horario, no hay marca en este bloque")
                    else:
                        total_font = QFont("Segoe UI", 10)
                        total_font.setBold(True)
                        item.setFont(total_font)
                        # Horas indicadas: verde opaco.
                        if col_idx in (total_asistencia_col, total_tardanza_col, salida_anticipada_col):
                            item.setBackground(indicated_bg)
                        # Horas extra: naranja opaco.
                        elif col_idx in (horas_extra_col, tardanza_extra_col, extra_incompleta_col):
                            item.setBackground(extra_bg)
                        # Faltas: rojo.
                        elif col_idx in (faltas_col, horas_deuda_col):
                            item.setBackground(faltas_bg)
                self.table.setItem(row_idx, col_idx, item)

        # Resaltado de columna completo (banda vertical), independiente del contenido.
        for row_idx in range(self.table.rowCount()):
            for c in (total_asistencia_col, total_tardanza_col, salida_anticipada_col):
                item = self.table.item(row_idx, c)
                if item is None:
                    item = QTableWidgetItem("")
                    self.table.setItem(row_idx, c, item)
                item.setBackground(indicated_bg)
            for c in (horas_extra_col, tardanza_extra_col, extra_incompleta_col):
                item = self.table.item(row_idx, c)
                if item is None:
                    item = QTableWidgetItem("")
                    self.table.setItem(row_idx, c, item)
                item.setBackground(extra_bg)
            for c in (faltas_col, horas_deuda_col):
                item_f = self.table.item(row_idx, c)
                if item_f is None:
                    item_f = QTableWidgetItem("")
                    self.table.setItem(row_idx, c, item_f)
                item_f.setBackground(faltas_bg)

        self.table.resizeRowsToContents()
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)

    def _load_schedule_rules(self) -> None:
        self._dept_weekdays = {}
        self._dept_day_start_minutes = {}
        self._schedule_aliases_by_dept = {}
        self._schedule_aliases_global = set()
        self._teacher_schedule_slots = {}
        self._day_schedule_aliases_by_dept = {}
        self._day_teacher_schedule_slots = {}
        self._day_teacher_modality_slots = {}
        self._day_schedule_name = {}
        self._schedule_teachers = []
        teacher_keys: set[str] = set()
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
                self._day_schedule_name[day] = schedule_path.stem
                aliases, slots = self._extract_rules_from_workbook(schedule_path)
                _m_aliases, _m_slots, modality_weekday = get_rules_with_modality(schedule_path)
                if aliases:
                    self._day_schedule_aliases_by_dept[day] = aliases
                if slots:
                    self._day_teacher_schedule_slots[day] = slots
                try:
                    weekday_for_day = self.report.period_start.replace(day=day).weekday()
                except ValueError:
                    weekday_for_day = -1
                day_modality: dict[str, dict[str, set[int]]] = {}
                if weekday_for_day >= 0:
                    for tkey, by_modality in modality_weekday.items():
                        for modality_name, by_weekday in by_modality.items():
                            slot_set = by_weekday.get(weekday_for_day, set())
                            if slot_set:
                                day_modality.setdefault(tkey, {}).setdefault(modality_name, set()).update(slot_set)
                if day_modality:
                    self._day_teacher_modality_slots[day] = day_modality
                for dept_key, alias_set in aliases.items():
                    self._schedule_aliases_by_dept.setdefault(dept_key, set()).update(alias_set)
                    self._schedule_aliases_global.update(alias_set)
                for tkey, by_weekday in slots.items():
                    target = self._teacher_schedule_slots.setdefault(tkey, {})
                    for weekday, slot_set in by_weekday.items():
                        target.setdefault(weekday, set()).update(slot_set)
                for tkey in slots.keys():
                    if tkey in teacher_keys:
                        continue
                    teacher_keys.add(tkey)
                    alias_key, dept_key = tkey.split("||", maxsplit=1)
                    self._schedule_teachers.append(
                        TeacherRecord(teacher_id="-", name=alias_key.upper(), department=dept_key.upper(), marks={})
                    )
        elif self._schedule_path.exists():
            aliases, slots = self._extract_rules_from_workbook(self._schedule_path)
            _m_aliases, _m_slots, modality_weekday = get_rules_with_modality(self._schedule_path)
            for dept_key, alias_set in aliases.items():
                self._schedule_aliases_by_dept.setdefault(dept_key, set()).update(alias_set)
                self._schedule_aliases_global.update(alias_set)
            for tkey, by_weekday in slots.items():
                target = self._teacher_schedule_slots.setdefault(tkey, {})
                for weekday, slot_set in by_weekday.items():
                    target.setdefault(weekday, set()).update(slot_set)
                if tkey not in teacher_keys:
                    teacher_keys.add(tkey)
                    alias_key, dept_key = tkey.split("||", maxsplit=1)
                    self._schedule_teachers.append(
                        TeacherRecord(teacher_id="-", name=alias_key.upper(), department=dept_key.upper(), marks={})
                    )
            day_modality: dict[str, dict[str, set[int]]] = {}
            for tkey, by_modality in modality_weekday.items():
                for modality_name, by_weekday in by_modality.items():
                    merged_slots: set[int] = set()
                    for slot_set in by_weekday.values():
                        merged_slots.update(slot_set)
                    if merged_slots:
                        day_modality.setdefault(tkey, {}).setdefault(modality_name, set()).update(merged_slots)
            if day_modality:
                self._day_teacher_modality_slots[0] = day_modality
        else:
            logger.info("Archivo de horario no encontrado: %s", self._schedule_path)

        if self._schedule_path.exists():
            try:
                workbook = load_horarios_workbook(self._schedule_path)
            except Exception:
                workbook = None
            if workbook is not None:
                for sheet in workbook.sheets:
                    for _, schedule_rows in extract_schedule_blocks_with_continuity(sheet.rows):
                        for row in schedule_rows:
                            for day_col in range(1, min(8, len(row))):
                                cell = (row[day_col] or "").strip()
                                if not cell:
                                    continue
                                pairs = extract_course_alias_pairs(cell)
                                if not pairs:
                                    continue
                                for course, _alias in pairs:
                                    dept_key = norm_name(course)
                                    self._dept_weekdays.setdefault(dept_key, set()).add(day_col - 1)
                                    slot_start = slot_start_minutes(row[0] if row else "")
                                    if slot_start is not None:
                                        day_map = self._dept_day_start_minutes.setdefault(dept_key, {})
                                        day_map.setdefault(day_col - 1, []).append(slot_start)
        for _, day_map in self._dept_day_start_minutes.items():
            for weekday, starts in day_map.items():
                day_map[weekday] = sorted(set(starts))

    def _extract_rules_from_workbook(self, xlsx_path: Path) -> tuple[dict[str, set[str]], dict[str, dict[int, set[int]]]]:
        return get_basic_rules(xlsx_path, continuity=True)

    def set_schedule_file(self, schedule_path: Path) -> None:
        self._schedule_path = schedule_path

    def clear_all(self) -> None:
        self.report = None
        self.filtered_teachers = []
        self._report_teachers_all = []
        self._schedule_teachers = []
        self._dept_weekdays = {}
        self._dept_day_start_minutes = {}
        self._schedule_aliases_by_dept = {}
        self._schedule_aliases_global = set()
        self._teacher_schedule_slots = {}
        self._day_schedule_aliases_by_dept = {}
        self._day_teacher_schedule_slots = {}
        self._day_schedule_name = {}
        self.search_box.clear()
        self.department_filter.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        while self.status_layout.count():
            item = self.status_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _compute_scheduled_tardiness_seconds(
        self,
        teacher: TeacherRecord,
        day: int,
        block_idx: int,
        cell_value: str,
    ) -> int:
        del teacher
        if not self.report or not self.report.period_start:
            return 0
        if self._is_non_working_day(day):
            return 0
        try:
            self.report.period_start.replace(day=day).weekday()
        except ValueError:
            return 0

        entry_minutes = first_time_minutes(cell_value)
        bounds = slot_bounds_minutes(block_idx)
        if entry_minutes is None or bounds is None:
            return 0
        expected_start, _ = bounds
        return max(entry_minutes - expected_start, 0) * 60

    def _is_scheduled_block(self, teacher: TeacherRecord, day: int, block_idx: int) -> bool:
        if not self.report or not self.report.period_start:
            return False
        try:
            weekday = self.report.period_start.replace(day=day).weekday()
        except ValueError:
            return False
        slots = scheduled_slots_for_teacher_weekday(
            teacher.teacher_id, teacher.name, teacher.department,
            self._slots_for_day(day), weekday,
        )
        return block_idx in slots

    def _count_teacher_faltas_seconds(self, teacher: TeacherRecord, allowed_days: set[int] | None = None) -> int:
        if not self.report:
            return 0
        total_missing_seconds = 0
        day_slot_values = self._build_day_slot_values(teacher)
        for day_pos, day in enumerate(self.report.days):
            if allowed_days is not None and day not in allowed_days:
                continue
            if self._is_non_working_day(day):
                continue
            for block_idx in range(self.REPORT_ROWS_PER_TEACHER):
                if not self._is_scheduled_block(teacher, day, block_idx):
                    continue
                if self._is_suspended_block(teacher, day, block_idx):
                    continue
                bounds = slot_bounds_minutes(block_idx)
                if bounds is None:
                    continue
                start_min, end_min = bounds
                slot_seconds = max((end_min - start_min) * 60, 0)
                if slot_seconds <= 0:
                    continue
                value = day_slot_values[day_pos][block_idx]
                if not value.strip():
                    total_missing_seconds += slot_seconds
        return total_missing_seconds

    def _count_teacher_debt_seconds(self, teacher: TeacherRecord, allowed_days: set[int] | None = None) -> int:
        if not self.report:
            return 0
        debt_seconds = 0
        for day in self.report.days:
            if allowed_days is not None and day not in allowed_days:
                continue
            for block_idx in range(self.REPORT_ROWS_PER_TEACHER):
                if not self._is_scheduled_block(teacher, day, block_idx):
                    continue
                if not (self._is_suspended_block(teacher, day, block_idx) or self._is_non_working_day(day)):
                    continue
                bounds = slot_bounds_minutes(block_idx)
                if bounds is None:
                    continue
                start_min, end_min = bounds
                debt_seconds += max((end_min - start_min) * 60, 0)
        return debt_seconds

    def _count_teacher_non_working_mark_seconds(self, teacher: TeacherRecord, allowed_days: set[int] | None = None) -> int:
        if not self.report:
            return 0
        total = 0
        for day in self.report.days:
            if allowed_days is not None and day not in allowed_days:
                continue
            if not self._is_non_working_day(day):
                continue
            mark_text = self._raw_mark_for_day(teacher, day)
            if mark_text.strip():
                raw_seconds = compute_seconds_from_mark_text(mark_text)
                hidden_assigned_seconds = 0
                for block_idx in range(self.REPORT_ROWS_PER_TEACHER):
                    if not self._is_scheduled_block(teacher, day, block_idx):
                        continue
                    hidden_assigned_seconds += slot_duration_seconds(block_idx)
                total += max(raw_seconds - hidden_assigned_seconds, 0)
        return total

    def _raw_mark_for_day(self, teacher: TeacherRecord, day: int) -> str:
        value = teacher.marks.get(day)
        if value is None:
            value = teacher.marks.get(str(day), "")
        return value or ""

    def _count_teacher_faltas(self, teacher: TeacherRecord, allowed_days: set[int] | None = None) -> int:
        """Compatibilidad: cuenta SOLO bloques programados vacios."""
        if not self.report:
            return 0
        total_blocks = 0
        day_slot_values = self._build_day_slot_values(teacher)
        for day_pos, day in enumerate(self.report.days):
            if allowed_days is not None and day not in allowed_days:
                continue
            if self._is_non_working_day(day):
                continue
            for block_idx in range(self.REPORT_ROWS_PER_TEACHER):
                if not self._is_scheduled_block(teacher, day, block_idx):
                    continue
                if self._is_suspended_block(teacher, day, block_idx):
                    continue
                value = day_slot_values[day_pos][block_idx]
                if not value.strip():
                    total_blocks += 1
        return total_blocks

    def _is_pending_regularization_block(self, block_text: str) -> bool:
        if "PENDIENTE" in (block_text or "").upper():
            return True
        minutes = self._normalized_event_minutes(block_text)
        return len(minutes) % 2 == 1

    def _is_excessively_early_entry(self, block_text: str, block_idx: int) -> bool:
        entry_minutes = first_time_minutes(block_text)
        bounds = slot_bounds_minutes(block_idx)
        if entry_minutes is None or bounds is None:
            return False
        slot_start, _ = bounds
        return entry_minutes < (slot_start - self.EARLY_PUNCTUAL_WINDOW_MINUTES)

    def _effective_block_seconds(self, block_text: str, block_idx: int) -> int:
        # Reglas en bloque programado:
        # - entrada_ajustada = max(entrada_real, hora_inicio_slot)
        # - salida_ajustada = min(salida_real, hora_fin_slot)
        # - no sumar tiempo antes de hora_inicio ni después de hora_fin
        # - salidas anticipadas descuentan automáticamente
        if not (0 <= block_idx < len(SLOT_START_MINUTES)):
            return compute_seconds_from_mark_text(block_text)
        bounds = slot_bounds_minutes(block_idx)
        if bounds is None:
            return compute_seconds_from_mark_text(block_text)
        slot_start, slot_end = bounds
        minutes = self._normalized_event_minutes(block_text)
        if len(minutes) < 2:
            return 0

        total_seconds = 0
        for idx in range(0, len(minutes) - 1, 2):
            entry_min = minutes[idx]
            exit_min = minutes[idx + 1]
            entry_adjusted = max(entry_min, slot_start)
            exit_adjusted = min(exit_min, slot_end)
            if exit_adjusted <= entry_adjusted:
                continue
            total_seconds += (exit_adjusted - entry_adjusted) * 60
        return max(total_seconds, 0)

    def _min_valid_seconds_for_scheduled_block(self, block_idx: int) -> int:
        bounds = slot_bounds_minutes(block_idx)
        if bounds is None:
            return self.MIN_VALID_ATTENDANCE_MINUTES * 60
        start_min, end_min = bounds
        slot_seconds = max((end_min - start_min) * 60, 0)
        base = self.MIN_VALID_ATTENDANCE_MINUTES * 60
        if slot_seconds <= 0:
            return base
        return min(base, slot_seconds)

    def _compute_teacher_extra_metrics(
        self,
        teacher: TeacherRecord,
        day_slot_values: list[list[str]],
        allowed_days: set[int] | None = None,
    ) -> tuple[int, int]:
        if not self.report or not self.report.period_start:
            return 0, 0
        extra_seconds = 0
        extra_tardy_seconds = 0
        for day_pos, day in enumerate(self.report.days):
            if allowed_days is not None and day not in allowed_days:
                continue
            if self._is_non_working_day(day):
                continue
            for block_idx in range(self.REPORT_ROWS_PER_TEACHER):
                value = day_slot_values[day_pos][block_idx]
                if not value.strip():
                    continue
                if self._is_scheduled_block(teacher, day, block_idx):
                    continue
                block_seconds, block_tardy_seconds = self._extra_block_metrics(value)
                if block_seconds < self.MIN_VALID_ATTENDANCE_MINUTES * 60:
                    continue
                extra_seconds += block_seconds
                extra_tardy_seconds += block_tardy_seconds
        return extra_seconds, extra_tardy_seconds

    def _compute_teacher_early_departure_minutes(
        self,
        teacher: TeacherRecord,
        day_slot_values: list[list[str]],
        allowed_days: set[int] | None = None,
    ) -> int:
        if not self.report:
            return 0
        total_minutes = 0
        for day_pos, day in enumerate(self.report.days):
            if allowed_days is not None and day not in allowed_days:
                continue
            if self._is_non_working_day(day):
                continue
            for block_idx in range(self.REPORT_ROWS_PER_TEACHER):
                if not self._is_scheduled_block(teacher, day, block_idx):
                    continue
                value = day_slot_values[day_pos][block_idx]
                if not value.strip() or self._is_pending_regularization_block(value):
                    continue
                total_minutes += self._early_departure_minutes_for_block(value, block_idx)
        return total_minutes

    def _early_departure_minutes_for_block(self, block_text: str, block_idx: int) -> int:
        bounds = slot_bounds_minutes(block_idx)
        if bounds is None:
            return 0
        _, slot_end = bounds
        minutes = self._normalized_event_minutes(block_text)
        if len(minutes) < 2:
            return 0
        # Para evitar sobreconteo, usar la salida mas tardia registrada en el bloque.
        latest_exit = max(minutes[idx + 1] for idx in range(0, len(minutes) - 1, 2))
        return max(slot_end - latest_exit, 0)

    def _compute_teacher_extra_early_departure_minutes(
        self,
        teacher: TeacherRecord,
        day_slot_values: list[list[str]],
        allowed_days: set[int] | None = None,
    ) -> int:
        if not self.report or not self.report.period_start:
            return 0
        total_minutes = 0
        for day_pos, day in enumerate(self.report.days):
            if allowed_days is not None and day not in allowed_days:
                continue
            if self._is_non_working_day(day):
                continue
            for block_idx in range(self.REPORT_ROWS_PER_TEACHER):
                if self._is_scheduled_block(teacher, day, block_idx):
                    continue
                value = day_slot_values[day_pos][block_idx]
                if not value.strip() or self._is_pending_regularization_block(value):
                    continue
                total_minutes += self._extra_early_departure_minutes_for_block(value)
        return total_minutes

    def _extra_early_departure_minutes_for_block(self, block_text: str) -> int:
        minutes = self._normalized_event_minutes(block_text)
        if len(minutes) < 2:
            return 0
        missing = 0
        for idx in range(0, len(minutes) - 1, 2):
            entry_real = minutes[idx]
            exit_real = minutes[idx + 1]
            if exit_real <= entry_real:
                continue
            plan = self._extra_planned_window(entry_real, exit_real)
            if plan is None:
                continue
            _entry_adjusted, _tardy_seconds, expected_end, _exit_adjusted = plan
            if exit_real < expected_end:
                missing += max(expected_end - exit_real, 0)
        return missing

    def _extra_block_metrics(self, block_text: str) -> tuple[int, int]:
        return extra_block_metrics(
            block_text,
            duplicate_window_minutes=self.DUPLICATE_MARK_WINDOW_MINUTES,
            extra_early_rounding_minutes=self.EXTRA_EARLY_ROUNDING_MINUTES,
            extra_block_minutes=self.EXTRA_BLOCK_MINUTES,
        )

    def _format_extra_expected_entry(self, entry_real: int) -> str:
        expected_start = (entry_real // 60) * 60
        next_hour = expected_start + 60
        adjusted = next_hour if (next_hour - entry_real) <= self.EXTRA_EARLY_ROUNDING_MINUTES else entry_real
        return f"{adjusted // 60:02d}:{adjusted % 60:02d}"

    def _normalize_extra_block_text(self, block_text: str) -> str:
        return normalize_extra_block_text(
            block_text,
            duplicate_window_minutes=self.DUPLICATE_MARK_WINDOW_MINUTES,
            extra_early_rounding_minutes=self.EXTRA_EARLY_ROUNDING_MINUTES,
            extra_block_minutes=self.EXTRA_BLOCK_MINUTES,
        )

    def _extra_planned_window(self, entry_real: int, exit_real: int) -> tuple[int, int, int, int] | None:
        return extra_planned_window(
            entry_real,
            exit_real,
            extra_early_rounding_minutes=self.EXTRA_EARLY_ROUNDING_MINUTES,
            extra_block_minutes=self.EXTRA_BLOCK_MINUTES,
        )

    def _build_day_slot_values(self, teacher: TeacherRecord) -> list[list[str]]:
        days = self.report.days if self.report else []
        return build_day_slot_values(
            teacher=teacher,
            days=days,
            report_rows_per_teacher=self.REPORT_ROWS_PER_TEACHER,
            duplicate_mark_window_minutes=self.DUPLICATE_MARK_WINDOW_MINUTES,
            extra_early_rounding_minutes=self.EXTRA_EARLY_ROUNDING_MINUTES,
            extra_block_minutes=self.EXTRA_BLOCK_MINUTES,
            min_valid_attendance_minutes=self.MIN_VALID_ATTENDANCE_MINUTES,
            early_punctual_window_minutes=self.EARLY_PUNCTUAL_WINDOW_MINUTES,
            scheduled_slots_for_day=lambda day: self._scheduled_slots_for_teacher_day(teacher, day),
        )

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
        existing_blocks = split_cell_blocks(current)
        if value in existing_blocks:
            return
        slot_values[slot_idx] = f"{current}\n_____\n{value}"

    def _scheduled_slots_for_teacher_day(self, teacher: TeacherRecord, day: int) -> set[int]:
        if not self.report or not self.report.period_start:
            return set()
        try:
            weekday = self.report.period_start.replace(day=day).weekday()
        except ValueError:
            return set()
        return scheduled_slots_for_teacher_weekday(
            teacher.teacher_id,
            teacher.name,
            teacher.department,
            self._slots_for_day(day),
            weekday,
        )

    def _extract_entry_exit_pairs(self, block_text: str) -> list[tuple[int, int]]:
        return extract_entry_exit_pairs(
            block_text,
            duplicate_window_minutes=self.DUPLICATE_MARK_WINDOW_MINUTES,
        )

    def _extract_trailing_unpaired_entry_minutes(self, block_text: str) -> int | None:
        return extract_trailing_unpaired_entry_minutes(
            block_text,
            duplicate_window_minutes=self.DUPLICATE_MARK_WINDOW_MINUTES,
        )

    def _extract_single_entry_minutes(self, block_text: str) -> int | None:
        return extract_single_entry_minutes(
            block_text,
            duplicate_window_minutes=self.DUPLICATE_MARK_WINDOW_MINUTES,
        )

    def _normalized_event_minutes(self, block_text: str) -> list[int]:
        return normalized_event_minutes(
            block_text,
            duplicate_window_minutes=self.DUPLICATE_MARK_WINDOW_MINUTES,
        )

    def _scheduled_slot_for_entry_minute(self, scheduled_slots: set[int], minute_value: int) -> int | None:
        ordered_slots = sorted(scheduled_slots)
        if not ordered_slots:
            return None

        # 1) Prioridad: ventana de entrada del slot (hasta 1h30 antes del inicio).
        for slot_idx in ordered_slots:
            bounds = slot_bounds_minutes(slot_idx)
            if bounds is None:
                continue
            start_min, _ = bounds
            if (start_min - self.EARLY_PUNCTUAL_WINDOW_MINUTES) <= minute_value <= start_min:
                return slot_idx

        # 2) Si no cae en ventana de entrada, usar pertenencia por rango del slot.
        for slot_idx in ordered_slots:
            bounds = slot_bounds_minutes(slot_idx)
            if bounds is None:
                continue
            start_min, end_min = bounds
            if start_min <= minute_value < end_min:
                return slot_idx

        # 3) Fallback: slot programado más cercano por inicio (evita salir del bloque esperado).
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
        if best_slot is not None:
            return best_slot
        return None

    def _aliases_for_day(self, day: int | None) -> dict[str, set[str]]:
        if day is not None and day in self._day_schedule_aliases_by_dept:
            return self._day_schedule_aliases_by_dept[day]
        return self._schedule_aliases_by_dept

    def _slots_for_day(self, day: int | None) -> dict[str, dict[int, set[int]]]:
        if day is not None and day in self._day_teacher_schedule_slots:
            return self._day_teacher_schedule_slots[day]
        return self._teacher_schedule_slots

    def _modality_slots_for_teacher_day(self, teacher: TeacherRecord, day: int) -> dict[str, set[int]]:
        day_map = self._day_teacher_modality_slots.get(day) or self._day_teacher_modality_slots.get(0, {})
        result: dict[str, set[int]] = {}
        for key in teacher_schedule_keys(teacher.teacher_id, teacher.name, teacher.department):
            by_modality = day_map.get(key, {})
            for modality_name, slot_set in by_modality.items():
                result.setdefault(modality_name, set()).update(slot_set)
        return result

    def _teacher_matches_schedule_any_day(self, teacher: TeacherRecord) -> bool:
        if self._day_schedule_aliases_by_dept:
            for aliases in self._day_schedule_aliases_by_dept.values():
                if teacher_exists_in_schedule(teacher.name, teacher.department, aliases):
                    return True
                if self._teacher_matches_any_alias_set(teacher.name, aliases):
                    return True
        return teacher_exists_in_schedule(teacher.name, teacher.department, self._schedule_aliases_by_dept) or self._teacher_matches_any_alias_set(teacher.name, self._schedule_aliases_by_dept)

    def _teacher_matches_any_alias_set(self, teacher_name: str, aliases_by_dept: dict[str, set[str]]) -> bool:
        tokens = [norm_name(t) for t in (teacher_name or "").split() if t.strip()]
        if not tokens:
            return False
        alias_union: set[str] = set()
        for alias_set in aliases_by_dept.values():
            alias_union.update(alias_set)
        for token in tokens:
            if token in alias_union:
                return True
        for alias in alias_union:
            alias_tokens = [tok for tok in alias.split() if tok]
            if any(token in alias_tokens for token in tokens):
                return True
        return False


    def _merge_report_with_schedule_teachers(self, csv_teachers: list[TeacherRecord]) -> list[TeacherRecord]:
        merged: list[TeacherRecord] = list(csv_teachers)
        existing = {f"{norm_name(t.name)}||{norm_name(t.department)}" for t in csv_teachers}
        for sch_teacher in self._schedule_teachers:
            key = f"{norm_name(sch_teacher.name)}||{norm_name(sch_teacher.department)}"
            if key not in existing:
                merged.append(sch_teacher)
                existing.add(key)
        return sorted(merged, key=lambda t: (t.name.lower(), t.department.lower(), t.teacher_id))

    def _period_title(self) -> str:
        if not self.report or not self.report.period_start:
            return "Mes analizado: No detectado"
        month_names = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
            7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
        }
        month_name = month_names.get(self.report.period_start.month, "Mes")
        return f"Mes analizado: {month_name} {self.report.period_start.year}"

    def _compatibility_status(self, report: AttendanceReport) -> tuple[bool, str]:
        if not report.days:
            return False, "No se detectaron dias del mes en el CSV."
        if not report.teachers:
            return False, "No se detectaron docentes en el CSV."
        if not self._schedule_teachers:
            return False, "No se detectaron docentes en HORARIOS.xlsx."

        matched = 0
        for t in report.teachers:
            matched_teacher = False
            if self._day_schedule_aliases_by_dept:
                for aliases in self._day_schedule_aliases_by_dept.values():
                    if teacher_exists_in_schedule(t.name, t.department, aliases) or self._teacher_matches_any_alias_set(t.name, aliases):
                        matched_teacher = True
                        break
            else:
                matched_teacher = teacher_exists_in_schedule(t.name, t.department, self._schedule_aliases_by_dept) or self._teacher_matches_any_alias_set(t.name, self._schedule_aliases_by_dept)
            if matched_teacher:
                matched += 1
        if matched == 0:
            return False, "Ningun docente del CSV coincide con el horario."

        return True, f"Docentes vinculados a horario: {matched}/{len(report.teachers)}."

    def _day_header_label(self, day: int) -> str:
        if not self.report or not self.report.period_start:
            return str(day)
        weekday_names = {0: "Lun", 1: "Mar", 2: "Mie", 3: "Jue", 4: "Vie", 5: "Sab", 6: "Dom"}
        try:
            current = self.report.period_start.replace(day=day)
            weekday = weekday_names.get(current.weekday(), "")
            return f"{day:02d} {weekday}"
        except ValueError:
            return str(day)

    def _set_status_chips(self, items: list[str]) -> None:
        while self.status_layout.count():
            item = self.status_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for text in items:
            chip = QLabel(text)
            upper = text.upper()
            if upper.startswith("ESTADO: COMPATIBLE"):
                chip.setObjectName("HorarioStatusChipOk")
            elif upper.startswith("ESTADO: NO COMPATIBLE"):
                chip.setObjectName("HorarioStatusChipBad")
            else:
                chip.setObjectName("HorarioStatusChip")
            chip.setAlignment(Qt.AlignCenter)
            self.status_layout.addWidget(chip)
        self.status_layout.addStretch(1)

    def _is_light_theme_active(self) -> bool:
        return self._theme_mode == "light"

    def _is_non_working_day(self, day: int) -> bool:
        if not self.report or not self.report.period_start:
            return False
        key = month_key(self.report.period_start.year, self.report.period_start.month)
        months = self._labor_calendar.get("months", {}) if isinstance(self._labor_calendar, dict) else {}
        month_data = months.get(key, {}) if isinstance(months, dict) else {}
        non_working = month_data.get("non_working_days", []) if isinstance(month_data, dict) else []
        try:
            non_working_set = {int(x) for x in non_working}
        except Exception:
            non_working_set = set()
        return day in non_working_set

    def _is_suspended_block(self, teacher: TeacherRecord, day: int, block_idx: int) -> bool:
        if not self.report or not self.report.period_start:
            return False
        key = month_key(self.report.period_start.year, self.report.period_start.month)
        months = self._labor_calendar.get("months", {}) if isinstance(self._labor_calendar, dict) else {}
        month_data = months.get(key, {}) if isinstance(months, dict) else {}
        suspensions = month_data.get("suspensions", []) if isinstance(month_data, dict) else []
        if not isinstance(suspensions, list):
            return False
        bounds = slot_bounds_minutes(block_idx)
        slot_start = bounds[0] if bounds else 0
        slot_end = bounds[1] if bounds else 0

        t_name = (teacher.name or "").strip().lower()

        for entry in suspensions:
            try:
                e_day = int(entry.get("day", -1))
            except Exception:
                continue
            if e_day != day:
                continue
            key_t = str(entry.get("teacher", "")).strip().lower()
            if key_t and key_t not in t_name:
                continue
            scope = str(entry.get("scope", "Todo el dia"))
            if scope == "Todo el dia":
                return True
            if scope == "Horario especifico":
                schedule_name = str(entry.get("schedule", "") or entry.get("slot", "")).strip()
                if not schedule_name:
                    continue
                modality_slots = self._modality_slots_for_teacher_day(teacher, day)
                selected_slots = modality_slots.get(schedule_name, set())
                if block_idx in selected_slots:
                    start = str(entry.get("start", "")).strip()
                    end = str(entry.get("end", "")).strip()
                    if start and end:
                        try:
                            sh, sm = [int(x) for x in start.split(":")]
                            eh, em = [int(x) for x in end.split(":")]
                            s_min = sh * 60 + sm
                            e_min = eh * 60 + em
                            if e_min <= s_min:
                                continue
                            overlap_start = max(slot_start, s_min)
                            overlap_end = min(slot_end, e_min)
                            if overlap_end <= overlap_start:
                                continue
                        except Exception:
                            continue
                    return True
            if scope in {"Turno manana", "Turno tarde"}:
                sch = str(entry.get("slot", "")).strip()
                idxs = slot_indexes_for_label(sch) if sch else []
                if idxs:
                    if block_idx in idxs:
                        return True
                    continue
                if scope == "Turno manana" and slot_end <= 14 * 60:
                    return True
                if scope == "Turno tarde" and slot_start >= 14 * 60:
                    return True
            if scope == "Rango de horas":
                start = str(entry.get("start", "")).strip()
                end = str(entry.get("end", "")).strip()
                try:
                    sh, sm = [int(x) for x in start.split(":")]
                    eh, em = [int(x) for x in end.split(":")]
                    s_min = sh * 60 + sm
                    e_min = eh * 60 + em
                    if e_min > s_min:
                        overlap_start = max(slot_start, s_min)
                        overlap_end = min(slot_end, e_min)
                        if overlap_end > overlap_start:
                            return True
                except Exception:
                    continue
        return False




