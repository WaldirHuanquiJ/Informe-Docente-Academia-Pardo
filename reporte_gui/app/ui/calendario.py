from __future__ import annotations

import calendar
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QSpinBox,
    QComboBox,
    QHeaderView,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QTimeEdit,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)
from PySide6.QtCore import QTime

from app.services.labor_calendar import load_calendar, month_key, save_calendar
from app.services.horario_excel import load_horarios_workbook
from app.services.schedule_rules_cache import get_basic_rules
from app.services.schedule_utils import extract_schedule_blocks
from app.ui.icon_factory import (
    make_check_all_icon,
    make_load_month_icon,
    make_save_icon,
    make_uncheck_all_icon,
)


class CalendarioView:
    _MESES_ES = {
        1: "Enero",
        2: "Febrero",
        3: "Marzo",
        4: "Abril",
        5: "Mayo",
        6: "Junio",
        7: "Julio",
        8: "Agosto",
        9: "Septiembre",
        10: "Octubre",
        11: "Noviembre",
        12: "Diciembre",
    }
    _DIAS_ES = {
        0: "Lunes",
        1: "Martes",
        2: "Miercoles",
        3: "Jueves",
        4: "Viernes",
        5: "Sabado",
        6: "Domingo",
    }

    def __init__(self, data_dir: Path) -> None:
        self.tab = QWidget()
        self._data_dir = data_dir
        self._schedule_path = self._data_dir / "HORARIOS.xlsx"
        self._payload = load_calendar(self._data_dir)
        self._loading_table = False
        self.on_calendar_updated: callable | None = None
        self._auto_save_timer = QTimer(self.tab)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(450)
        self._auto_save_timer.timeout.connect(self._flush_calendar_changes)

        self.title = QLabel("Calendario Laboral del Mes")
        self.title.setProperty("role", "heroTitle")

        self.year_combo = QSpinBox()
        self.year_combo.setRange(1900, 9999)
        self.year_combo.setObjectName("CalendarioSpin")
        current_year = datetime.now().year
        self.year_combo.setValue(current_year)

        self.month_combo = QSpinBox()
        self.month_combo.setRange(1, 12)
        self.month_combo.setObjectName("CalendarioSpin")
        self.month_combo.setValue(datetime.now().month)
        self.month_name_label = QLabel("")
        self.month_name_label.setObjectName("HorarioStatusChip")

        self.btn_load = QPushButton("Cargar")
        self.btn_save = QPushButton("Guardar")
        self.btn_mark_all = QPushButton("Marcar todos")
        self.btn_mark_none = QPushButton("Desmarcar todos")
        self.btn_load.setObjectName("actionImport")
        self.btn_save.setObjectName("actionExport")
        self.btn_mark_all.setObjectName("actionImport")
        self.btn_mark_none.setObjectName("actionClear")
        self.btn_load.setIcon(make_load_month_icon(20))
        self.btn_mark_all.setIcon(make_check_all_icon(20))
        self.btn_mark_none.setIcon(make_uncheck_all_icon(20))
        self.btn_save.setIcon(make_save_icon(20))
        self.btn_load.setIconSize(QSize(20, 20))
        self.btn_mark_all.setIconSize(QSize(20, 20))
        self.btn_mark_none.setIconSize(QSize(20, 20))
        self.btn_save.setIconSize(QSize(20, 20))

        self.table = QTableWidget()
        self.table.setObjectName("CalendarioTable")
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Dia", "Fecha", "Laborable", "Dia", "Fecha", "Laborable"]
        )
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet(
            "QTableWidget#CalendarioTable::indicator { width: 14px; height: 14px; }"
            "QTableWidget#CalendarioTable::indicator:checked {"
            " image: none; border: 1px solid #166534; background-color: #22c55e; }"
            "QTableWidget#CalendarioTable::indicator:unchecked {"
            " image: none; border: 1px solid #991b1b; background-color: #ef4444; }"
        )

        self.susp_scope_combo = QComboBox()
        self.susp_scope_combo.setObjectName("CalendarioField")
        self.susp_scope_combo.addItems(
            ["Todo el dia", "Turno manana", "Turno tarde", "Horario especifico", "Rango de horas"]
        )
        self.susp_day_spin = QSpinBox()
        self.susp_day_spin.setRange(1, 31)
        self.susp_day_spin.setObjectName("CalendarioSpin")
        self.susp_start_time = QTimeEdit()
        self.susp_start_time.setObjectName("CalendarioTime")
        self.susp_start_time.setDisplayFormat("HH:mm")
        self.susp_start_time.setTime(QTime(7, 0))
        self.susp_end_time = QTimeEdit()
        self.susp_end_time.setObjectName("CalendarioTime")
        self.susp_end_time.setDisplayFormat("HH:mm")
        self.susp_end_time.setTime(QTime(9, 0))
        self.susp_slot_input = QLineEdit()
        self.susp_slot_input.setObjectName("CalendarioField")
        self.susp_slot_input.setPlaceholderText("07:00-14:00 o 14:00-20:00")
        self.susp_schedule_combo = QComboBox()
        self.susp_schedule_combo.setObjectName("CalendarioField")
        self.susp_schedule_combo.setMinimumContentsLength(24)
        self.susp_schedule_mode_combo = QComboBox()
        self.susp_schedule_mode_combo.setObjectName("CalendarioField")
        self.susp_schedule_mode_combo.addItems(["Dia completo", "Por horas"])
        self.susp_teacher_combo = QComboBox()
        self.susp_teacher_combo.setObjectName("CalendarioField")
        self.susp_teacher_combo.setMinimumContentsLength(24)
        self.btn_susp_add = QPushButton("Agregar suspension")
        self.btn_susp_remove = QPushButton("Quitar seleccion")
        self.btn_susp_add.setObjectName("actionImport")
        self.btn_susp_remove.setObjectName("actionClear")
        self.btn_susp_add.setIcon(make_check_all_icon(20))
        self.btn_susp_remove.setIcon(make_uncheck_all_icon(20))
        self.btn_susp_add.setIconSize(QSize(20, 20))
        self.btn_susp_remove.setIconSize(QSize(20, 20))

        self.susp_table = QTableWidget()
        self.susp_table.setObjectName("CalendarioSuspTable")
        self.susp_table.setColumnCount(4)
        self.susp_table.setHorizontalHeaderLabels(
            ["Fecha", "Alcance", "Detalle", "Docente"]
        )
        self.susp_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.susp_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.susp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.susp_table.setMaximumHeight(220)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(QLabel("A\u00f1o:"))
        controls.addWidget(self.year_combo)
        controls.addWidget(QLabel("Mes:"))
        controls.addWidget(self.month_combo)
        controls.addWidget(self.month_name_label)
        controls.addWidget(self.btn_load)
        controls.addWidget(self.btn_mark_all)
        controls.addWidget(self.btn_mark_none)
        controls.addWidget(self.btn_save)
        controls.addStretch(1)

        layout = QVBoxLayout()
        layout.addWidget(self.title)
        layout.addLayout(controls)
        main_row = QHBoxLayout()
        main_row.setSpacing(10)
        main_row.addWidget(self.table, 3)
        susp_group = QGroupBox("Suspensiones del mes")
        susp_group.setObjectName("CalendarioSuspGroup")
        susp_form = QFormLayout()
        self._lbl_susp_day = QLabel("Dia:")
        self._lbl_susp_scope = QLabel("Alcance:")
        self._lbl_susp_hours = QLabel("Horas:")
        self._lbl_susp_slot = QLabel("Horario:")
        self._lbl_susp_schedule = QLabel("Horario:")
        self._lbl_susp_schedule_mode = QLabel("Modo:")
        self._lbl_susp_teacher = QLabel("Docente:")
        susp_form.addRow(self._lbl_susp_day, self.susp_day_spin)
        susp_form.addRow(self._lbl_susp_scope, self.susp_scope_combo)
        hour_row = QHBoxLayout()
        hour_row.addWidget(self.susp_start_time)
        hour_row.addWidget(QLabel("a"))
        hour_row.addWidget(self.susp_end_time)
        hour_wrap = QWidget()
        hour_wrap.setLayout(hour_row)
        self._hours_wrap = hour_wrap
        susp_form.addRow(self._lbl_susp_hours, self._hours_wrap)
        susp_form.addRow(self._lbl_susp_slot, self.susp_slot_input)
        susp_form.addRow(self._lbl_susp_schedule, self.susp_schedule_combo)
        susp_form.addRow(self._lbl_susp_schedule_mode, self.susp_schedule_mode_combo)
        susp_form.addRow(self._lbl_susp_teacher, self.susp_teacher_combo)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_susp_add)
        btn_row.addWidget(self.btn_susp_remove)
        btn_row.addStretch(1)
        btn_wrap = QWidget()
        btn_wrap.setLayout(btn_row)
        susp_form.addRow("", btn_wrap)
        susp_group.setLayout(susp_form)
        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)
        right_panel.addWidget(susp_group)
        right_panel.addWidget(self.susp_table)
        right_wrap = QWidget()
        right_wrap.setLayout(right_panel)
        main_row.addWidget(right_wrap, 2)
        layout.addLayout(main_row)
        self.tab.setLayout(layout)

        self.btn_load.clicked.connect(self._load_month)
        self.btn_save.clicked.connect(self._save_month)
        self.btn_mark_all.clicked.connect(self._mark_all_working)
        self.btn_mark_none.clicked.connect(self._mark_all_non_working)
        self.month_combo.valueChanged.connect(self._sync_month_name)
        self.table.itemChanged.connect(self._on_item_changed)
        self.susp_scope_combo.currentTextChanged.connect(self._sync_susp_inputs)
        self.susp_schedule_mode_combo.currentTextChanged.connect(self._sync_susp_inputs)
        self.btn_susp_add.clicked.connect(self._add_suspension)
        self.btn_susp_remove.clicked.connect(self._remove_selected_suspension)
        self._sync_month_name()
        self._load_teacher_options()
        self._load_schedule_options()
        self._restore_ui_state()
        self._sync_susp_inputs()
        self._load_month()

    def _selected_year_month(self) -> tuple[int, int]:
        year = int(self.year_combo.value())
        month = int(self.month_combo.value())
        return year, month

    def _load_month(self) -> None:
        year, month = self._selected_year_month()
        self._sync_month_name()
        key = month_key(year, month)
        month_data = self._payload.get("months", {}).get(key, {})
        non_working_days = {int(d) for d in month_data.get("non_working_days", [])}
        suspensions = month_data.get("suspensions", []) if isinstance(month_data, dict) else []

        _, days_in_month = calendar.monthrange(year, month)
        left_count = (days_in_month + 1) // 2
        self._loading_table = True
        self.table.setRowCount(left_count)
        for row in range(left_count):
            for col in range(6):
                self.table.setItem(row, col, QTableWidgetItem(""))

        for day in range(1, days_in_month + 1):
            base_col = 0 if day <= left_count else 3
            row = (day - 1) if day <= left_count else (day - left_count - 1)
            dow = self._DIAS_ES.get(datetime(year, month, day).weekday(), "")
            self.table.item(row, base_col + 0).setText(f"{day:02d} ({dow})")
            self.table.item(row, base_col + 1).setText(f"{year:04d}-{month:02d}-{day:02d}")

            laborable = QTableWidgetItem("")
            laborable.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            laborable.setCheckState(Qt.Unchecked if day in non_working_days else Qt.Checked)
            laborable.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, base_col + 2, laborable)
            self._apply_day_color(row, base_col)

        self._loading_table = False
        self.table.resizeColumnsToContents()
        self._load_suspensions_table(suspensions)

    def _save_month(self) -> None:
        self._auto_save_timer.stop()
        self._persist_month(show_message=True, notify=True)

    def _persist_month(self, show_message: bool = False, notify: bool = True) -> None:
        year, month = self._selected_year_month()
        key = month_key(year, month)
        non_working_days: list[int] = []
        _, days_in_month = calendar.monthrange(year, month)
        left_count = (days_in_month + 1) // 2
        for day in range(1, days_in_month + 1):
            base_col = 0 if day <= left_count else 3
            row = (day - 1) if day <= left_count else (day - left_count - 1)
            item = self.table.item(row, base_col + 2)
            if item is None or item.checkState() != Qt.Checked:
                non_working_days.append(day)

        months = self._payload.setdefault("months", {})
        months[key] = {
            "non_working_days": non_working_days,
            "suspensions": self._collect_suspensions_from_table(),
        }
        self._payload["ui_state"] = self._collect_ui_state()
        save_calendar(self._data_dir, self._payload)
        if show_message:
            QMessageBox.information(self.tab, "Calendario", "Calendario guardado correctamente.")
        if notify and callable(self.on_calendar_updated):
            self.on_calendar_updated()

    def _schedule_calendar_save(self) -> None:
        self._auto_save_timer.start()

    def _flush_calendar_changes(self) -> None:
        self._persist_month(show_message=False, notify=True)

    def _mark_all_working(self) -> None:
        self._loading_table = True
        for row in range(self.table.rowCount()):
            for col in (2, 5):
                item = self.table.item(row, col)
                if item is not None and item.flags() & Qt.ItemIsUserCheckable:
                    item.setCheckState(Qt.Checked)
            self._apply_day_color(row, 0)
            self._apply_day_color(row, 3)
        self._loading_table = False
        self._schedule_calendar_save()

    def _mark_all_non_working(self) -> None:
        self._loading_table = True
        for row in range(self.table.rowCount()):
            for col in (2, 5):
                item = self.table.item(row, col)
                if item is not None and item.flags() & Qt.ItemIsUserCheckable:
                    item.setCheckState(Qt.Unchecked)
            self._apply_day_color(row, 0)
            self._apply_day_color(row, 3)
        self._loading_table = False
        self._schedule_calendar_save()

    def refresh_icons(self) -> None:
        self.btn_load.setIcon(make_load_month_icon(20))
        self.btn_mark_all.setIcon(make_check_all_icon(20))
        self.btn_mark_none.setIcon(make_uncheck_all_icon(20))
        self.btn_save.setIcon(make_save_icon(20))
        self.btn_susp_add.setIcon(make_check_all_icon(20))
        self.btn_susp_remove.setIcon(make_uncheck_all_icon(20))

    def _sync_month_name(self) -> None:
        month = int(self.month_combo.value())
        self.month_name_label.setText(self._MESES_ES.get(month, "Mes"))
        try:
            year, month_v = self._selected_year_month()
            _w, days_in_month = calendar.monthrange(year, month_v)
            self.susp_day_spin.setMaximum(days_in_month)
        except Exception:
            self.susp_day_spin.setMaximum(31)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading_table:
            return
        if item.column() not in (2, 5):
            return
        base_col = 0 if item.column() == 2 else 3
        self._apply_day_color(item.row(), base_col)
        self._schedule_calendar_save()

    def _apply_day_color(self, row: int, base_col: int) -> None:
        day_item = self.table.item(row, base_col + 0)
        date_item = self.table.item(row, base_col + 1)
        check_item = self.table.item(row, base_col + 2)
        if day_item is None or date_item is None or check_item is None:
            return
        is_working = check_item.checkState() == Qt.Checked
        is_light = self.tab.palette().window().color().lightness() > 160
        if is_working:
            # Contraste alto para que se note claramente en ambos temas.
            bg = QColor("#dcfce7") if is_light else QColor("#0f2f21")
            fg = QColor("#166534") if is_light else QColor("#7dffb2")
            label = "Laborable"
        else:
            # En oscuro: rojo muy claro casi blanco; en claro: rojo oscuro.
            bg = QColor("#fee2e2") if is_light else QColor("#fff5f5")
            fg = QColor("#7f1d1d") if is_light else QColor("#ef4444")
            label = "No laborable"
        for it in (day_item, date_item, check_item):
            it.setBackground(bg)
            it.setForeground(fg)
            font = it.font()
            font.setBold(True)
            it.setFont(font)
        check_item.setText(label)
        self.table.viewport().update()

    def _sync_susp_inputs(self) -> None:
        scope = self.susp_scope_combo.currentText()
        is_full_day = scope == "Todo el dia"
        is_shift = scope in {"Turno manana", "Turno tarde"}
        is_schedule = scope == "Horario especifico"
        is_range = scope == "Rango de horas"
        is_schedule_by_hours = is_schedule and self.susp_schedule_mode_combo.currentText() == "Por horas"
        show_hours = is_range or is_schedule_by_hours

        # Todo el dia: ocultar opciones extra.
        self._lbl_susp_hours.setVisible(not is_full_day and show_hours)
        self._hours_wrap.setVisible(not is_full_day and show_hours)
        self._lbl_susp_slot.setVisible(is_shift)
        self.susp_slot_input.setVisible(is_shift)
        self._lbl_susp_schedule.setVisible(is_schedule)
        self.susp_schedule_combo.setVisible(is_schedule)
        self._lbl_susp_schedule_mode.setVisible(is_schedule)
        self.susp_schedule_mode_combo.setVisible(is_schedule)
        self._lbl_susp_teacher.setVisible(is_range)
        self.susp_teacher_combo.setVisible(is_range)

        self.susp_start_time.setEnabled(show_hours)
        self.susp_end_time.setEnabled(show_hours)
        self.susp_slot_input.setEnabled(is_shift)
        self.susp_schedule_combo.setEnabled(is_schedule)
        self.susp_schedule_mode_combo.setEnabled(is_schedule)
        self.susp_teacher_combo.setEnabled(is_range)
        if scope == "Turno manana" and not self.susp_slot_input.text().strip():
            self.susp_slot_input.setText("07:00-14:00")
        elif scope == "Turno tarde" and not self.susp_slot_input.text().strip():
            self.susp_slot_input.setText("14:00-20:00")

    def _load_suspensions_table(self, suspensions: list[dict]) -> None:
        self.susp_table.setRowCount(0)
        for entry in suspensions:
            day = int(entry.get("day", 0))
            scope = str(entry.get("scope", "Todo el dia"))
            start = str(entry.get("start", ""))
            end = str(entry.get("end", ""))
            teacher = str(entry.get("teacher", ""))
            slot = str(entry.get("slot", ""))
            schedule = str(entry.get("schedule", ""))
            if scope == "Rango de horas" and start and end:
                detail = f"{start}-{end}"
            elif scope == "Horario especifico" and schedule:
                detail = f"{schedule} | {start}-{end}" if start and end else schedule
            elif scope in {"Turno manana", "Turno tarde"} and slot:
                detail = slot
            else:
                detail = "-"
            self._append_suspension_row(day, scope, detail, teacher or "-")

    def _append_suspension_row(self, day: int, scope: str, detail: str, teacher: str = "-") -> None:
        year, month = self._selected_year_month()
        row = self.susp_table.rowCount()
        self.susp_table.insertRow(row)
        self.susp_table.setItem(row, 0, QTableWidgetItem(f"{year:04d}-{month:02d}-{day:02d}"))
        self.susp_table.setItem(row, 1, QTableWidgetItem(scope))
        self.susp_table.setItem(row, 2, QTableWidgetItem(detail))
        self.susp_table.setItem(row, 3, QTableWidgetItem(teacher))

    def _add_suspension(self) -> None:
        year, month = self._selected_year_month()
        _w, days_in_month = calendar.monthrange(year, month)
        day = int(self.susp_day_spin.value())
        if day < 1 or day > days_in_month:
            QMessageBox.warning(self.tab, "Suspension", "El dia no es valido para el mes seleccionado.")
            return
        scope = self.susp_scope_combo.currentText()
        teacher = "-"
        if scope == "Rango de horas":
            start = self.susp_start_time.time().toString("HH:mm")
            end = self.susp_end_time.time().toString("HH:mm")
            detail = f"{start}-{end}"
            teacher = (self.susp_teacher_combo.currentText() or "-").strip()
            if teacher == "-":
                QMessageBox.warning(self.tab, "Suspension", "Seleccione un docente para rango de horas.")
                return
        elif scope in {"Turno manana", "Turno tarde"}:
            detail = (self.susp_slot_input.text() or "").strip()
            if not detail:
                QMessageBox.warning(self.tab, "Suspension", "Seleccione el horario que se suspende.")
                return
        elif scope == "Horario especifico":
            schedule = (self.susp_schedule_combo.currentText() or "").strip()
            if not schedule or schedule == "-":
                QMessageBox.warning(self.tab, "Suspension", "Seleccione el horario de la pestaña Horario.")
                return
            if self.susp_schedule_mode_combo.currentText() == "Por horas":
                start = self.susp_start_time.time().toString("HH:mm")
                end = self.susp_end_time.time().toString("HH:mm")
                detail = f"{schedule} | {start}-{end}"
            else:
                detail = schedule
        else:
            detail = "-"
        self._append_suspension_row(day, scope, detail, teacher)
        self._schedule_calendar_save()

    def _remove_selected_suspension(self) -> None:
        row = self.susp_table.currentRow()
        if row < 0:
            return
        self.susp_table.removeRow(row)
        self._schedule_calendar_save()

    def _collect_suspensions_from_table(self) -> list[dict]:
        out: list[dict] = []
        for row in range(self.susp_table.rowCount()):
            date_text = (self.susp_table.item(row, 0).text() if self.susp_table.item(row, 0) else "").strip()
            scope = (self.susp_table.item(row, 1).text() if self.susp_table.item(row, 1) else "").strip()
            detail = (self.susp_table.item(row, 2).text() if self.susp_table.item(row, 2) else "").strip()
            teacher = (self.susp_table.item(row, 3).text() if self.susp_table.item(row, 3) else "").strip()
            try:
                day = int(date_text.split("-")[-1])
            except Exception:
                continue
            entry = {"day": day, "scope": scope}
            if scope == "Rango de horas" and "-" in detail:
                start, end = detail.split("-", maxsplit=1)
                entry["start"] = start.strip()
                entry["end"] = end.strip()
            if scope in {"Turno manana", "Turno tarde"} and detail and detail != "-":
                entry["slot"] = detail
            if scope == "Horario especifico" and detail and detail != "-":
                schedule = detail
                hours = ""
                if "|" in detail:
                    schedule, hours = detail.split("|", maxsplit=1)
                    schedule = schedule.strip()
                    hours = hours.strip()
                entry["schedule"] = schedule
                if hours and "-" in hours:
                    start, end = hours.split("-", maxsplit=1)
                    entry["start"] = start.strip()
                    entry["end"] = end.strip()
            if scope == "Rango de horas" and teacher and teacher != "-":
                entry["teacher"] = teacher
            out.append(entry)
        return out

    def set_schedule_file(self, schedule_path: Path) -> None:
        self._schedule_path = schedule_path
        self._load_teacher_options()
        self._load_schedule_options()

    def _collect_ui_state(self) -> dict:
        return {
            "year": int(self.year_combo.value()),
            "month": int(self.month_combo.value()),
            "scope": self.susp_scope_combo.currentText(),
            "slot": self.susp_slot_input.text().strip(),
            "schedule": self.susp_schedule_combo.currentText(),
            "schedule_mode": self.susp_schedule_mode_combo.currentText(),
            "teacher": self.susp_teacher_combo.currentText(),
            "start": self.susp_start_time.time().toString("HH:mm"),
            "end": self.susp_end_time.time().toString("HH:mm"),
        }

    def _restore_ui_state(self) -> None:
        state = self._payload.get("ui_state", {})
        if not isinstance(state, dict):
            return
        try:
            year = int(state.get("year", self.year_combo.value()))
            month = int(state.get("month", self.month_combo.value()))
            if 1900 <= year <= 9999:
                self.year_combo.setValue(year)
            if 1 <= month <= 12:
                self.month_combo.setValue(month)
        except Exception:
            pass

        scope = str(state.get("scope", "")).strip()
        if scope:
            idx = self.susp_scope_combo.findText(scope)
            if idx >= 0:
                self.susp_scope_combo.setCurrentIndex(idx)

        slot = str(state.get("slot", "")).strip()
        if slot:
            self.susp_slot_input.setText(slot)

        schedule = str(state.get("schedule", "")).strip()
        if schedule:
            idx = self.susp_schedule_combo.findText(schedule)
            if idx >= 0:
                self.susp_schedule_combo.setCurrentIndex(idx)

        schedule_mode = str(state.get("schedule_mode", "")).strip()
        if schedule_mode:
            idx = self.susp_schedule_mode_combo.findText(schedule_mode)
            if idx >= 0:
                self.susp_schedule_mode_combo.setCurrentIndex(idx)

        teacher = str(state.get("teacher", "")).strip()
        if teacher:
            idx = self.susp_teacher_combo.findText(teacher)
            if idx >= 0:
                self.susp_teacher_combo.setCurrentIndex(idx)

        start = str(state.get("start", "")).strip()
        end = str(state.get("end", "")).strip()
        start_time = QTime.fromString(start, "HH:mm")
        end_time = QTime.fromString(end, "HH:mm")
        if start_time.isValid():
            self.susp_start_time.setTime(start_time)
        if end_time.isValid():
            self.susp_end_time.setTime(end_time)

    def _load_teacher_options(self) -> None:
        teachers: set[str] = set()
        try:
            if self._schedule_path.exists():
                _aliases, slots = get_basic_rules(self._schedule_path, continuity=False)
                for tkey in slots.keys():
                    if "||" not in tkey:
                        continue
                    alias, _dept = tkey.split("||", maxsplit=1)
                    alias = alias.strip().upper()
                    if alias:
                        teachers.add(alias)
        except Exception:
            teachers = set()
        self.susp_teacher_combo.clear()
        if not teachers:
            self.susp_teacher_combo.addItem("-")
            return
        self.susp_teacher_combo.addItems(sorted(teachers))

    def _load_schedule_options(self) -> None:
        options: list[str] = []
        try:
            if self._schedule_path.exists():
                workbook = load_horarios_workbook(self._schedule_path)
                for sheet in workbook.sheets:
                    blocks = extract_schedule_blocks(sheet.rows)
                    if len(blocks) <= 1:
                        options.append(sheet.name)
                    else:
                        for block_idx, _block in enumerate(blocks):
                            options.append(f"{sheet.name} - T{block_idx + 1}")
        except Exception:
            options = []
        current = self.susp_schedule_combo.currentText()
        self.susp_schedule_combo.clear()
        if not options:
            self.susp_schedule_combo.addItem("-")
            return
        unique_options = sorted(set(options), key=lambda x: x.lower())
        self.susp_schedule_combo.addItems(unique_options)
        idx = self.susp_schedule_combo.findText(current)
        if idx >= 0:
            self.susp_schedule_combo.setCurrentIndex(idx)


