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
from app.services.schedule_rules_cache import get_basic_rules
from app.services.schedule_versions import resolve_schedule_for_date
from app.ui.icon_factory import make_import_icon, make_clear_icon
from app.services.logging_config import get_logger
from app.services.session_store import load_session, save_session
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
    teacher_exists_in_schedule,
)
from app.services.time_rules import (
    compute_seconds_from_mark_text,
    split_cell_blocks,
)
from app.ui.engine_loader import load_ui_engine

slot_engine = load_ui_engine(__file__, "reporte", "engine_slots")
metrics_engine = load_ui_engine(__file__, "reporte", "engine_metrics")
table_engine = load_ui_engine(__file__, "reporte", "engine_table")
schedule_engine = load_ui_engine(__file__, "reporte", "engine_schedule")

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
    MIN_VALID_ATTENDANCE_MINUTES = 70
    EARLY_PUNCTUAL_WINDOW_MINUTES = 90
    DUPLICATE_MARK_WINDOW_MINUTES = 20
    EXTRA_EARLY_ROUNDING_MINUTES = 30
    EXTRA_BLOCK_MINUTES = 120
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
        self._day_schedule_name: dict[int, str] = {}
        self._schedule_teachers: list[TeacherRecord] = []
        self._report_teachers_all: list[TeacherRecord] = []
        self._theme_mode: str = "dark"
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
        return table_engine.theme_column_colors(self)

    def _apply_theme_to_current_table(self) -> None:
        table_engine.apply_theme_to_current_table(self)

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
        table_engine.refresh_table(self)

    def _load_schedule_rules(self) -> None:
        schedule_engine.load_schedule_rules(self)

    def _extract_rules_from_workbook(self, xlsx_path: Path) -> tuple[dict[str, set[str]], dict[str, dict[int, set[int]]]]:
        return schedule_engine.extract_rules_from_workbook(self, xlsx_path)

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
        return metrics_engine.compute_scheduled_tardiness_seconds(
            self, teacher, day, block_idx, cell_value
        )

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

    def _count_teacher_faltas(self, teacher: TeacherRecord, allowed_days: set[int] | None = None) -> int:
        return metrics_engine.count_teacher_faltas(self, teacher, allowed_days)

    def _is_pending_regularization_block(self, block_text: str) -> bool:
        return metrics_engine.is_pending_regularization_block(self, block_text)

    def _is_excessively_early_entry(self, block_text: str, block_idx: int) -> bool:
        return metrics_engine.is_excessively_early_entry(self, block_text, block_idx)

    def _effective_block_seconds(self, block_text: str, block_idx: int) -> int:
        return metrics_engine.effective_block_seconds(self, block_text, block_idx)

    def _compute_teacher_extra_metrics(
        self,
        teacher: TeacherRecord,
        day_slot_values: list[list[str]],
        allowed_days: set[int] | None = None,
    ) -> tuple[int, int]:
        return metrics_engine.compute_teacher_extra_metrics(
            self, teacher, day_slot_values, allowed_days
        )

    def _compute_teacher_early_departure_minutes(
        self,
        teacher: TeacherRecord,
        day_slot_values: list[list[str]],
        allowed_days: set[int] | None = None,
    ) -> int:
        return metrics_engine.compute_teacher_early_departure_minutes(
            self, teacher, day_slot_values, allowed_days
        )

    def _early_departure_minutes_for_block(self, block_text: str, block_idx: int) -> int:
        return metrics_engine.early_departure_minutes_for_block(self, block_text, block_idx)

    def _compute_teacher_extra_early_departure_minutes(
        self,
        teacher: TeacherRecord,
        day_slot_values: list[list[str]],
        allowed_days: set[int] | None = None,
    ) -> int:
        return metrics_engine.compute_teacher_extra_early_departure_minutes(
            self, teacher, day_slot_values, allowed_days
        )

    def _extra_early_departure_minutes_for_block(self, block_text: str) -> int:
        return metrics_engine.extra_early_departure_minutes_for_block(self, block_text)

    def _extra_block_metrics(self, block_text: str) -> tuple[int, int]:
        return metrics_engine.extra_block_metrics(self, block_text)

    def _format_extra_expected_entry(self, entry_real: int) -> str:
        return metrics_engine.format_extra_expected_entry(self, entry_real)

    def _normalize_extra_block_text(self, block_text: str) -> str:
        return metrics_engine.normalize_extra_block_text(self, block_text)

    def _extra_planned_window(self, entry_real: int, exit_real: int) -> tuple[int, int, int, int] | None:
        return metrics_engine.extra_planned_window(self, entry_real, exit_real)

    def _build_day_slot_values(self, teacher: TeacherRecord) -> list[list[str]]:
        return slot_engine.build_day_slot_values(self, teacher)

    def _append_slot_value(self, slot_values: list[str], slot_idx: int, text: str) -> None:
        slot_engine.append_slot_value(self, slot_values, slot_idx, text)

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
        return slot_engine.extract_entry_exit_pairs(self, block_text)

    def _extract_trailing_unpaired_entry_minutes(self, block_text: str) -> int | None:
        return slot_engine.extract_trailing_unpaired_entry_minutes(self, block_text)

    def _extract_single_entry_minutes(self, block_text: str) -> int | None:
        return slot_engine.extract_single_entry_minutes(self, block_text)

    def _normalized_event_minutes(self, block_text: str) -> list[int]:
        return slot_engine.normalized_event_minutes(self, block_text)

    def _scheduled_slot_for_entry_minute(self, scheduled_slots: set[int], minute_value: int) -> int | None:
        return slot_engine.scheduled_slot_for_entry_minute(self, scheduled_slots, minute_value)

    def _aliases_for_day(self, day: int | None) -> dict[str, set[str]]:
        if day is not None and day in self._day_schedule_aliases_by_dept:
            return self._day_schedule_aliases_by_dept[day]
        return self._schedule_aliases_by_dept

    def _slots_for_day(self, day: int | None) -> dict[str, dict[int, set[int]]]:
        if day is not None and day in self._day_teacher_schedule_slots:
            return self._day_teacher_schedule_slots[day]
        return self._teacher_schedule_slots

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
