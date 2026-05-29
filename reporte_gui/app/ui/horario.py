from __future__ import annotations

import csv
import re
import unicodedata
from datetime import date
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, QDate
from PySide6.QtGui import QFont, QIcon, QTransform
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLayout,
    QLayoutItem,
    QLabel,
    QHeaderView,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models import TeacherRecord
from app.services.horario_excel import WorkbookData, load_horarios_workbook
from app.services.logging_config import get_logger
from app.services.schedule_versions import list_versioned_schedules, resolve_schedule_for_date
from app.services.session_store import load_session, save_session
from app.services.schedule_utils import (
    HEADER_NAMES,
    TIME_SLOTS,
    extract_schedule_blocks_with_continuity,
    norm,
    norm_name,
)
from app.ui.icon_factory import make_refresh_icon, make_import_icon, make_clear_icon, make_export_icon

logger = get_logger(__name__)


class FlowLayout(QLayout):
    def __init__(self, parent: QWidget | None = None, margin: int = 0, hspacing: int = 6, vspacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self._hspacing = hspacing
        self._vspacing = vspacing

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(+margins.left(), +margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._hspacing
            if next_x - self._hspacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + self._vspacing
                next_x = x + hint.width() + self._hspacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class HorarioView:
    _SLOT_RE = re.compile(r"\s+")
    _BREAK_RE = re.compile(r"DESCAN[DS]O(?:\s+TARDE)?", re.IGNORECASE)
    _ALIAS_SPLIT_RE = re.compile(r"\s*(?:/|,|;|\||&|\+|\bY\b)\s*", re.IGNORECASE)
    _PAIR_SPLIT_RE = re.compile(r"\s*(?:\n+|//|;;)\s*")
    _SESSION_KEY_IMPORT_DIR = "last_import_horario_dir"

    def __init__(self, data_dir: Path) -> None:
        self.tab = QWidget()
        self._data_dir = data_dir
        self._schedule_dir = self._data_dir / "horario"
        self._schedule_dir.mkdir(parents=True, exist_ok=True)
        self._schedule_path = self._schedule_dir / "HORARIOS.xlsx"
        self._workbook: WorkbookData | None = None
        self._teachers: list[TeacherRecord] = []
        self.on_import_horario: callable | None = None
        self.on_clear: callable | None = None

        self._teacher_course_map: dict[str, set[str]] = {}
        self._teacher_global_cells: dict[str, dict[tuple[int, int], list[str]]] = {}
        self._teacher_global_hours: dict[str, float] = {}
        self._teacher_group_hours: dict[str, dict[str, float]] = {}
        self._teacher_by_key: dict[str, TeacherRecord] = {}
        self._known_courses_norm: set[str] = set()
        self._sheet_views: list[tuple[int, str | None]] = []
        self._available_schedule_versions: list[tuple[date, Path]] = []
        self._updating_date_selector = False
        self._selected_schedule_date: date | None = None

        self.title = QLabel("Horarios")
        self.title.setProperty("role", "panelTitle")
        self.title.setAlignment(Qt.AlignCenter)

        self.sheet_selector = QComboBox()
        self.sheet_selector.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.sheet_selector.setMinimumContentsLength(18)
        self.sheet_selector.currentIndexChanged.connect(self._on_sheet_changed)

        self.teacher_selector = QComboBox()
        self.teacher_selector.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.teacher_selector.setMinimumContentsLength(24)
        self.teacher_selector.currentIndexChanged.connect(self._render_selected_sheet)

        self.block_selector = QComboBox()
        self.block_selector.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.block_selector.setMinimumContentsLength(16)
        self.block_selector.currentIndexChanged.connect(self._on_block_changed)

        self.refresh_button = QPushButton("Refrescar")
        self.refresh_button.setMaximumWidth(150)
        refresh_icon = make_refresh_icon(20)
        self._refresh_base_icon = refresh_icon
        self._refresh_angle = 0
        self._refresh_anim_timer = QTimer(self.tab)
        self._refresh_anim_timer.setInterval(40)
        self._refresh_anim_timer.timeout.connect(self._animate_refresh_icon)
        self.refresh_button.setIcon(refresh_icon)
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        self.import_horario_button = QPushButton("Importar Horario")
        self.import_horario_button.setMaximumWidth(180)
        self.import_horario_button.clicked.connect(self._on_import_horario_clicked)
        self.clear_button = QPushButton("Limpiar")
        self.clear_button.setMaximumWidth(120)
        self.clear_button.clicked.connect(self._on_clear_clicked)
        self.export_teachers_button = QPushButton("Exportar Docentes")
        self.export_teachers_button.setMaximumWidth(190)
        self.export_teachers_button.clicked.connect(self._on_export_teachers_clicked)
        import_icon = make_import_icon(20)
        clear_icon = make_clear_icon(20)
        export_icon = make_export_icon(20)
        self.import_horario_button.setIcon(import_icon)
        self.import_horario_button.setObjectName("actionImport")
        self.clear_button.setIcon(clear_icon)
        self.clear_button.setObjectName("actionClear")
        self.export_teachers_button.setIcon(export_icon)
        self.export_teachers_button.setObjectName("actionExport")
        self.refresh_button.setIconSize(QSize(20, 20))
        self.import_horario_button.setIconSize(QSize(20, 20))
        self.clear_button.setIconSize(QSize(20, 20))
        self.export_teachers_button.setIconSize(QSize(20, 20))
        self._apply_rounded_buttons(
            self.refresh_button,
            self.import_horario_button,
            self.clear_button,
            self.export_teachers_button,
        )

        self.status = QLabel("Cargando horarios...")
        self.status.hide()

        self.status_host = QWidget()
        self.status_host.setObjectName("HorarioStatusHost")
        self.status_layout = QHBoxLayout()
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_layout.setSpacing(6)
        self.status_host.setLayout(self.status_layout)
        self.date_label = QLabel("Fecha:")
        self.date_label.setObjectName("HorarioStatusChip")
        self.schedule_date_selector = QDateEdit()
        self.schedule_date_selector.setCalendarPopup(True)
        self.schedule_date_selector.setDisplayFormat("dd/MM/yyyy")
        self.schedule_date_selector.setMinimumWidth(140)
        self.schedule_date_selector.setObjectName("HorarioDatePicker")
        self.schedule_date_selector.dateChanged.connect(self._on_schedule_date_changed)
        cal = self.schedule_date_selector.calendarWidget()
        cal.setObjectName("HorarioCalendarPopup")

        self.summary_host = QWidget()
        self.summary_host.setObjectName("HorarioSummary")
        self.summary_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.summary_layout = FlowLayout(self.summary_host, margin=2, hspacing=5, vspacing=5)
        self.summary_host.setLayout(self.summary_layout)

        self.table = QTableWidget()
        self.table.setObjectName("HorarioTable")
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().setMinimumSectionSize(44)

        top = QHBoxLayout()
        top.addWidget(QLabel("Horario:"))
        top.addWidget(self.sheet_selector)
        top.addWidget(QLabel("Turno:"))
        top.addWidget(self.block_selector)
        top.addWidget(self.refresh_button)
        top.addWidget(self.import_horario_button)
        top.addWidget(self.clear_button)
        top.addWidget(QLabel("Docente:"))
        top.addWidget(self.teacher_selector)
        top.addStretch(1)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addLayout(top)
        layout.addWidget(self.status_host)
        layout.addWidget(self.table)
        layout.addWidget(self.summary_host)

        self.tab.setLayout(layout)
        self.clear_all()

    def _apply_rounded_buttons(self, *buttons: QPushButton) -> None:
        for btn in buttons:
            current = btn.styleSheet() or ""
            btn.setStyleSheet(
                current
                + "\nQPushButton { border-radius: 14px; min-height: 25px; max-height: 25px; padding: 4px 12px; }"
            )

    def refresh_icons(self) -> None:
        self._refresh_base_icon = make_refresh_icon(20)
        self.refresh_button.setIcon(self._refresh_base_icon)
        self.import_horario_button.setIcon(make_import_icon(20))
        self.clear_button.setIcon(make_clear_icon(20))
        self.export_teachers_button.setIcon(make_export_icon(20))

    def set_teachers(self, teachers: list[TeacherRecord]) -> None:
        self._teachers = teachers
        teacher_courses = {self._tchr_norm_name(t.department) for t in teachers if t.department.strip()}
        self._known_courses_norm |= teacher_courses
        self._build_global_teacher_index()
        self._build_teacher_filter()
        self._render_selected_sheet()

    def reload(self) -> None:
        self._refresh_schedule_date_selector()
        xlsx_path = self._schedule_path
        if not xlsx_path.exists():
            self.status.setText(f"No se encontro {xlsx_path.name} en data")
            logger.warning("Archivo de horario no encontrado: %s", xlsx_path)
            self.sheet_selector.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        self._workbook = load_horarios_workbook(xlsx_path)
        self._known_courses_norm = self._collect_known_courses_from_workbook(self._workbook)

        self.sheet_selector.blockSignals(True)
        self.sheet_selector.clear()
        self._sheet_views = []
        for idx, sheet in enumerate(self._workbook.sheets):
            variants = self._sheet_variants_for_name(sheet.name)
            for variant in variants:
                self._sheet_views.append((idx, variant))
                self.sheet_selector.addItem(self._sheet_view_name(sheet.name, variant))
        self.sheet_selector.blockSignals(False)

        if self.sheet_selector.count() > 0:
            self.sheet_selector.setCurrentIndex(0)
            self._build_global_teacher_index()
            self._build_teacher_filter()
            self._render_selected_sheet()
        else:
            self.status.setText("El archivo no contiene hojas visibles")

    def _refresh_schedule_date_selector(self) -> None:
        self._available_schedule_versions = list_versioned_schedules(self._schedule_dir)
        self._updating_date_selector = True
        try:
            if self._available_schedule_versions:
                self.schedule_date_selector.setMinimumDate(QDate(2000, 1, 1))
                self.schedule_date_selector.setMaximumDate(QDate(2100, 12, 31))
                target = self._selected_schedule_date
                if target is None:
                    today = date.today()
                    target = today
                    selected_today = resolve_schedule_for_date(self._schedule_dir, today, None)
                    if selected_today is None:
                        selected_today = self._available_schedule_versions[0][1]
                    self._schedule_path = selected_today
                self._selected_schedule_date = target
                self.schedule_date_selector.setDate(QDate(target.year, target.month, target.day))
                self.schedule_date_selector.setEnabled(True)
            else:
                today = QDate.currentDate()
                self.schedule_date_selector.setDate(today)
                self.schedule_date_selector.setEnabled(False)
        finally:
            self._updating_date_selector = False

    def _on_schedule_date_changed(self, qdate: QDate) -> None:
        if self._updating_date_selector:
            return
        if not self._available_schedule_versions:
            return
        target = date(qdate.year(), qdate.month(), qdate.day())
        self._selected_schedule_date = target
        selected = resolve_schedule_for_date(self._schedule_dir, target, None)
        if selected is None:
            # Si la fecha es anterior al primer horario, usamos el primero disponible.
            selected = self._available_schedule_versions[0][1]
        if selected.resolve() == self._schedule_path.resolve():
            return
        self._schedule_path = selected
        self.reload()

    def set_schedule_file(self, schedule_path: Path) -> None:
        self._schedule_path = schedule_path
        self._schedule_dir = schedule_path.parent
        dt = None
        for version_date, path in self._available_schedule_versions:
            if path.resolve() == schedule_path.resolve():
                dt = version_date
                break
        self._selected_schedule_date = dt

    def clear_all(self) -> None:
        self._workbook = None
        self._teachers = []
        self._teacher_course_map = {}
        self._teacher_global_cells = {}
        self._teacher_global_hours = {}
        self._teacher_group_hours = {}
        self._teacher_by_key = {}
        self._known_courses_norm = set()
        self._sheet_views = []
        self._available_schedule_versions = []
        self._selected_schedule_date = None
        self.sheet_selector.clear()
        self.block_selector.clear()
        self.teacher_selector.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        while self.summary_layout.count():
            item = self.summary_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        while self.status_layout.count():
            item = self.status_layout.takeAt(0)
            widget = item.widget()
            if widget and widget not in {self.date_label, self.schedule_date_selector, self.export_teachers_button}:
                widget.deleteLater()

    def _collect_known_courses_from_workbook(self, workbook: WorkbookData) -> set[str]:
        known: set[str] = set()
        for sheet in workbook.sheets:
            blocks = extract_schedule_blocks_with_continuity(sheet.rows)
            for _, schedule_rows in blocks:
                for row in schedule_rows:
                    for c in range(1, min(len(row), 8)):
                        text = (row[c] or "").strip()
                        if not text:
                            continue
                        for part in [p.strip() for p in self._PAIR_SPLIT_RE.split(text) if p.strip()]:
                            compact = " ".join(part.split())
                            if " " not in compact:
                                continue
                            course = compact.split(" ", 1)[0].strip()
                            course_norm = self._tchr_norm_name(course)
                            if course_norm and len(course_norm) >= 3:
                                known.add(course_norm)
        return known

    def _on_refresh_clicked(self) -> None:
        self._refresh_angle = 0
        self._refresh_anim_timer.start()
        self.reload()

    def _on_import_horario_clicked(self) -> None:
        session = load_session(self._data_dir)
        start_dir = session.get(self._SESSION_KEY_IMPORT_DIR, str(Path.home() / "Documents"))
        file_paths, _ = QFileDialog.getOpenFileNames(
            self.tab,
            "Seleccionar archivo(s) de horario",
            start_dir,
            "Excel (*.xlsx *.xls);;Todos los archivos (*.*)",
        )
        if not file_paths:
            return
        selected_paths = [Path(p) for p in file_paths]
        session[self._SESSION_KEY_IMPORT_DIR] = str(selected_paths[0].parent)
        save_session(self._data_dir, session)
        if callable(self.on_import_horario):
            self.on_import_horario(selected_paths)

    def _on_clear_clicked(self) -> None:
        if callable(self.on_clear):
            self.on_clear()

    def _on_export_teachers_clicked(self) -> None:
        versioned = list_versioned_schedules(self._schedule_dir)
        if not versioned:
            return

        rows: list[tuple[str, str, str]] = []
        # docente, curso, modalidad
        for version_date, schedule_path in versioned:
            workbook = load_horarios_workbook(schedule_path)
            for sheet in workbook.sheets:
                modality_name = (sheet.name or "").strip().upper()
                blocks = extract_schedule_blocks_with_continuity(sheet.rows)
                for _headers, schedule_rows in blocks:
                    for row in schedule_rows:
                        for day_col in range(1, min(8, len(row))):
                            cell = (row[day_col] or "").strip()
                            if not cell:
                                continue
                            pairs = self._extract_course_alias_pairs(cell)
                            if not pairs:
                                continue
                            for course, aliases in pairs:
                                course_name = (course or "").strip()
                                if not course_name:
                                    continue
                                for alias in aliases:
                                    teacher_name = (alias or "").strip().upper()
                                    if not teacher_name:
                                        continue
                                    rows.append((teacher_name, course_name.upper(), modality_name))

        if not rows:
            return

        merged: dict[tuple[str, str], set[str]] = {}
        for docente, curso, modalidad in rows:
            key = (docente, curso)
            merged.setdefault(key, set()).add(modalidad)

        unique_rows = sorted(
            [
                (docente, curso, " | ".join(sorted(modalidades)))
                for (docente, curso), modalidades in merged.items()
            ],
            key=lambda x: (
                self._tchr_norm_name(x[0]),
                self._tchr_norm_name(x[1]),
            ),
        )
        default_name = f"DOCENTES_HORARIO_{date.today().strftime('%Y%m%d')}.csv"
        target_path, _ = QFileDialog.getSaveFileName(
            self.tab,
            "Exportar lista de docentes (todas las versiones)",
            str((self._schedule_dir / default_name).resolve()),
            "CSV (*.csv)",
        )
        if not target_path:
            return
        with open(target_path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(["N°", "docente", "curso", "modalidad"])
            for idx, (docente, curso, modalidad) in enumerate(unique_rows, start=1):
                writer.writerow([idx, docente, curso, modalidad])

    def _animate_refresh_icon(self) -> None:
        self._refresh_angle += 24
        size = self.refresh_button.iconSize()
        if size.width() <= 0 or size.height() <= 0:
            self._refresh_anim_timer.stop()
            self.refresh_button.setIcon(self._refresh_base_icon)
            return
        pixmap = self._refresh_base_icon.pixmap(size)
        transform = QTransform().rotate(self._refresh_angle)
        rotated = pixmap.transformed(transform, Qt.SmoothTransformation)
        self.refresh_button.setIcon(QIcon(rotated))
        if self._refresh_angle >= 360:
            self._refresh_anim_timer.stop()
            self.refresh_button.setIcon(self._refresh_base_icon)

    def _render_selected_sheet(self) -> None:
        if not self._workbook:
            return

        idx = self.sheet_selector.currentIndex()
        if idx < 0 or idx >= len(self._sheet_views):
            return

        sheet_idx, variant = self._sheet_views[idx]
        sheet = self._workbook.sheets[sheet_idx]
        view_name = self._sheet_view_name(sheet.name, variant)
        blocks = extract_schedule_blocks_with_continuity(sheet.rows)
        projected_blocks = [
            (hdr, self._project_schedule_rows(rows, variant))
            for hdr, rows in blocks
        ]
        self._sync_block_selector(projected_blocks)

        block_idx = self.block_selector.currentIndex()
        if block_idx < 0:
            block_idx = 0

        headers, schedule_rows = projected_blocks[block_idx] if projected_blocks else (HEADER_NAMES, [[""] * 8 for _ in TIME_SLOTS])

        selected_teacher = self._selected_teacher_key()
        if selected_teacher:
            teacher_obj = self._teacher_by_key.get(selected_teacher)
            headers, schedule_rows = self._render_teacher_merged(selected_teacher)
            total_hours = self._teacher_global_hours.get(selected_teacher, 0.0)
            display_name = teacher_obj.name if teacher_obj else selected_teacher
            self._set_status_chips(
                [
                    f"Docente: {display_name.upper()}",
                    f"Total de horas: {total_hours:.1f} h",
                    "Cruces: celdas con varias entradas",
                ]
            )
            items = self._build_daily_hours_summary_items(schedule_rows)
            items.extend(self._build_teacher_groups_summary_items(selected_teacher))
            self._set_summary_chips(items)
        else:
            self._set_status_chips([f"Mostrando: {view_name}", f"Turnos: {len(projected_blocks)}"])
            self._set_summary_chips(self._build_group_hours_summary_items(schedule_rows))

        visible_cols = min(7, max(0, len(headers) - 1))
        self.table.setColumnCount(visible_cols)
        self.table.setHorizontalHeaderLabels(headers[1 : 1 + visible_cols])
        self.table.setRowCount(len(schedule_rows))
        self.table.setVerticalHeaderLabels([(row[0] if row else "") for row in schedule_rows])

        bold_font = QFont()
        bold_font.setBold(True)

        for r, row in enumerate(schedule_rows):
            for c, value in enumerate(row[1 : 1 + visible_cols]):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, item)

        self.table.verticalHeader().setFont(bold_font)

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        viewport_width = max(self.table.viewport().width(), 1)
        equal_width = max(150, (viewport_width // max(1, visible_cols)) - 2)
        for c in range(visible_cols):
            self.table.setColumnWidth(c, equal_width)

        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.resizeRowsToContents()

    def _build_teacher_filter(self) -> None:
        current_teacher = self._selected_teacher_key()
        self.teacher_selector.blockSignals(True)
        self.teacher_selector.clear()
        self.teacher_selector.addItem("Todos los docentes", "")

        filtered_keys = sorted(
            [k for k, courses in self._teacher_course_map.items() if courses],
            key=lambda k: (
                self._teacher_by_key.get(k).name.lower() if self._teacher_by_key.get(k) else k.lower(),
                self._teacher_by_key.get(k).department.lower() if self._teacher_by_key.get(k) else "",
            ),
        )
        for key in filtered_keys:
            teacher = self._teacher_by_key.get(key)
            if not teacher:
                continue
            courses = sorted(self._teacher_course_map.get(key, set()))
            suffix = f" | {', '.join(courses)}" if courses else ""
            self.teacher_selector.addItem(
                f"{teacher.name} ({teacher.department}){suffix}",
                key,
            )

        idx = self.teacher_selector.findData(current_teacher)
        self.teacher_selector.setCurrentIndex(idx if idx >= 0 else 0)
        self.teacher_selector.blockSignals(False)

    def _build_global_teacher_index(self) -> None:
        self._teacher_by_key = {self._teacher_key(t): t for t in self._teachers}
        self._teacher_course_map = {k: set() for k in self._teacher_by_key}
        self._teacher_global_cells = {k: {} for k in self._teacher_by_key}
        self._teacher_global_hours = {k: 0.0 for k in self._teacher_by_key}
        self._teacher_group_hours = {k: {} for k in self._teacher_by_key}

        if not self._workbook or not self._teachers:
            if not self._workbook:
                return

        for sheet_idx, sheet in enumerate(self._workbook.sheets):
            blocks = extract_schedule_blocks_with_continuity(sheet.rows)
            for block_idx, (_, schedule_rows) in enumerate(blocks):
                turno_name = "Manana" if len(blocks) == 1 or block_idx == 0 else ("Tarde" if block_idx == 1 else f"T{block_idx+1}")
                variants = self._sheet_variants_for_name(sheet.name)
                for variant in variants:
                    projected_rows = self._project_schedule_rows(schedule_rows, variant)
                    view_name = self._sheet_view_name(sheet.name, variant)

                    for r, row in enumerate(projected_rows):
                        for c in range(1, min(len(row), 8)):
                            text = (row[c] or "").strip()
                            if not text:
                                continue
                            pairs = self._extract_course_alias_pairs(text)
                            if not pairs:
                                continue

                            for course, alias_candidates in pairs:
                                if not alias_candidates:
                                    continue
                                pair_target_keys: set[str] = set()
                                for alias in alias_candidates:
                                    matched_this_alias = False
                                    # 1) Vincula con docentes ya existentes (CSV) si coincide alias + curso.
                                    for teacher in self._teachers:
                                        key_teacher = self._teacher_key(teacher)
                                        aliases = self._teacher_aliases(teacher.name)
                                        if not self._alias_matches_teacher(alias, aliases):
                                            continue
                                        if course and self._tchr_norm_name(course) != self._tchr_norm_name(teacher.department):
                                            continue
                                        pair_target_keys.add(key_teacher)
                                        matched_this_alias = True

                                    # 2) Si no existe en CSV, crea docente desde horario para que se visualice.
                                    if not matched_this_alias:
                                        skey = self._schedule_teacher_key(alias, course)
                                        if skey not in self._teacher_by_key:
                                            self._teacher_by_key[skey] = TeacherRecord(
                                                teacher_id="-",
                                                name=alias.upper(),
                                                department=(course.upper() if course else "(SIN CURSO)"),
                                                marks={},
                                            )
                                            self._teacher_course_map[skey] = set()
                                            self._teacher_global_cells[skey] = {}
                                            self._teacher_global_hours[skey] = 0.0
                                            self._teacher_group_hours[skey] = {}
                                        pair_target_keys.add(skey)

                                for key_teacher in pair_target_keys:
                                    if course:
                                        self._teacher_course_map.setdefault(key_teacher, set()).add(course)
                                    key = (r, c)
                                    src = f"{course} [{view_name}/{turno_name}]".strip()
                                    self._teacher_global_cells.setdefault(key_teacher, {}).setdefault(key, []).append(src)
                                    slot_h = self._slot_hours(TIME_SLOTS[r])
                                    self._teacher_global_hours[key_teacher] = self._teacher_global_hours.get(key_teacher, 0.0) + slot_h
                                    self._teacher_group_hours.setdefault(key_teacher, {})
                                    self._teacher_group_hours[key_teacher][view_name] = (
                                        self._teacher_group_hours[key_teacher].get(view_name, 0.0) + slot_h
                                    )

    def _sheet_variants_for_name(self, sheet_name: str) -> list[str | None]:
        m = re.search(r"\b([A-Z])\-([A-Z])\b", sheet_name.upper())
        if m:
            return [m.group(1), m.group(2)]
        return [None]

    def _sheet_view_name(self, sheet_name: str, variant: str | None) -> str:
        if variant is None:
            return sheet_name
        m = re.search(r"\b([A-Z])\-([A-Z])\b", sheet_name, flags=re.IGNORECASE)
        if m:
            return sheet_name[: m.start()] + variant + sheet_name[m.end() :]
        return f"{sheet_name} {variant}"

    def _project_schedule_rows(self, schedule_rows: list[list[str]], variant: str | None) -> list[list[str]]:
        if variant is None:
            return schedule_rows
        index = 0 if variant in {"A", "C", "E", "G", "I"} else 1
        projected: list[list[str]] = []
        for row in schedule_rows:
            if not row:
                projected.append([""] * 8)
                continue
            out = list(row[:8]) + [""] * max(0, 8 - len(row))
            out = out[:8]
            for c in range(1, 8):
                text = (out[c] or "").strip()
                if not text:
                    continue
                pairs = self._extract_course_alias_pairs(text)
                if not pairs:
                    continue
                # Regla de compartido: si solo hay un par, aplica para ambos grupos.
                pick_idx = index if len(pairs) > 1 else 0
                if pick_idx < len(pairs):
                    course, aliases = pairs[pick_idx]
                    alias_text = " / ".join(aliases)
                    out[c] = f"{course}\n{alias_text}".strip()
                else:
                    out[c] = ""
            projected.append(out)
        return projected

    def _render_teacher_merged(self, teacher_key: str) -> tuple[list[str], list[list[str]]]:
        rows = [[slot, "", "", "", "", "", "", ""] for slot in TIME_SLOTS]
        cells = self._teacher_global_cells.get(teacher_key, {})
        for (r, c), values in cells.items():
            if 0 <= r < len(rows) and 1 <= c <= 7:
                unique_values: list[str] = []
                for v in values:
                    if v not in unique_values:
                        unique_values.append(v)
                rows[r][c] = "\n".join(unique_values)
        return HEADER_NAMES, rows

    def _selected_teacher_key(self) -> str:
        return str(self.teacher_selector.currentData() or "")

    def _on_sheet_changed(self) -> None:
        # Al cambiar de horario/grupo, volver a vista normal (sin docente filtrado).
        if self.teacher_selector.currentIndex() != 0:
            self.teacher_selector.blockSignals(True)
            self.teacher_selector.setCurrentIndex(0)
            self.teacher_selector.blockSignals(False)
        self._render_selected_sheet()

    def _on_block_changed(self) -> None:
        # Al cambiar de turno, volver a vista normal (sin docente filtrado).
        if self.teacher_selector.currentIndex() != 0:
            self.teacher_selector.blockSignals(True)
            self.teacher_selector.setCurrentIndex(0)
            self.teacher_selector.blockSignals(False)
        self._render_selected_sheet()

    def _teacher_key(self, teacher: TeacherRecord) -> str:
        return f"{teacher.teacher_id}||{teacher.name}||{teacher.department}"

    def _schedule_teacher_key(self, alias: str, course: str) -> str:
        return f"SCH||{self._tchr_norm_name(alias)}||{self._tchr_norm_name(course)}"

    def _extract_course_alias_pairs(self, cell_text: str) -> list[tuple[str, list[str]]]:
        raw = (cell_text or "").strip()
        if not raw:
            return []

        # Caso tipico del Excel: CURSO en una linea y DOCENTE en la siguiente.
        # Si hay 2+ lineas, las emparejamos de 2 en 2 para conservar A/B correctamente.
        line_parts = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        paired_parts: list[str] = []
        if len(line_parts) >= 2:
            idx = 0
            while idx + 1 < len(line_parts):
                paired_parts.append(f"{line_parts[idx]} {line_parts[idx + 1]}")
                idx += 2
            if idx < len(line_parts):
                paired_parts.append(line_parts[idx])

        parts = [p.strip() for p in self._PAIR_SPLIT_RE.split(raw) if p.strip()]
        if paired_parts:
            parts = paired_parts
        if not parts:
            parts = [raw]

        pairs: list[tuple[str, list[str]]] = []
        for part in parts:
            compact = " ".join(part.split())
            if " " not in compact:
                continue
            tokens = compact.split()
            current_course = tokens[0].strip()
            alias_tokens: list[str] = []

            def flush_pair(course_value: str, alias_parts: list[str]) -> None:
                alias_raw_inner = " ".join(alias_parts).strip()
                if not course_value or not alias_raw_inner:
                    return
                aliases: list[str] = [alias_raw_inner]
                for piece in self._ALIAS_SPLIT_RE.split(alias_raw_inner):
                    clean = piece.strip()
                    if clean:
                        aliases.append(clean)
                unique: list[str] = []
                seen: set[str] = set()
                for alias in aliases:
                    key = self._tchr_norm_name(alias)
                    if key and key not in seen:
                        seen.add(key)
                        unique.append(alias)
                if unique:
                    pairs.append((course_value.strip(), unique))

            for tk in tokens[1:]:
                tk_norm = self._tchr_norm_name(tk)
                if alias_tokens and tk_norm in self._known_courses_norm:
                    flush_pair(current_course, alias_tokens)
                    current_course = tk
                    alias_tokens = []
                else:
                    alias_tokens.append(tk)

            flush_pair(current_course, alias_tokens)
        return pairs

    def _teacher_aliases(self, teacher_name: str) -> list[str]:
        norm_str = self._tchr_norm_name(teacher_name)
        tokens = [t for t in norm_str.split() if t]
        aliases: list[str] = []
        for token in tokens:
            aliases.append(token)
            # Alias corto controlado (>=5) para casos como MOSTA -> MOSTACERO.
            if len(token) >= 5:
                aliases.append(token[:5])
        return sorted(set(a for a in aliases if a), key=len, reverse=True)

    def _alias_matches_teacher(self, alias: str, teacher_aliases: list[str]) -> bool:
        norm_alias = self._tchr_norm_name(alias).replace(" ", "")
        if not norm_alias:
            return False

        alias_set = {a.replace(" ", "") for a in teacher_aliases if a.strip()}
        # Regla 1: igualdad exacta de alias.
        if norm_alias in alias_set:
            return True

        # Regla 2: prefijo solo si alias tiene longitud >= 5 (evita Alex/Alexander).
        if len(norm_alias) >= 5:
            for a in alias_set:
                if a.startswith(norm_alias):
                    return True
        return False

    def _tchr_norm_name(self, text: str) -> str:
        """Normaliza nombre de docente para matching: sin tildes, mayúsculas, solo letras y números."""
        base = unicodedata.normalize("NFD", text or "")
        base = "".join(ch for ch in base if unicodedata.category(ch) != "Mn")
        return re.sub(r"[^A-Z0-9 ]+", " ", base.upper()).strip()

    def _sync_block_selector(self, blocks: list[tuple[list[str], list[list[str]]]]) -> None:
        labels: list[str] = []
        if len(blocks) == 1:
            labels = ["Turno Unificado (Manana y Tarde)"]
        else:
            for idx in range(len(blocks)):
                if idx == 0:
                    labels.append("Turno Manana")
                elif idx == 1:
                    labels.append("Turno Tarde")
                else:
                    labels.append(f"Turno {idx + 1}")

        current = self.block_selector.currentText()
        self.block_selector.blockSignals(True)
        self.block_selector.clear()
        self.block_selector.addItems(labels or ["Turno"])
        if current in labels:
            self.block_selector.setCurrentIndex(labels.index(current))
        else:
            self.block_selector.setCurrentIndex(0)
        self.block_selector.blockSignals(False)

    def _slot_hours(self, slot_label: str) -> float:
        parts = slot_label.split("-")
        if len(parts) != 2:
            return 0.0
        try:
            h1, m1 = [int(x) for x in parts[0].strip().split(":")]
            h2, m2 = [int(x) for x in parts[1].strip().split(":")]
            return max(((h2 * 60 + m2) - (h1 * 60 + m1)) / 60.0, 0.0)
        except Exception:
            return 0.0

    def _build_daily_hours_summary_items(self, schedule_rows: list[list[str]]) -> list[str]:
        day_names = HEADER_NAMES[1:]
        day_hours = [0.0] * 7
        for row in schedule_rows:
            slot_hours = self._slot_hours(row[0] if row else "")
            for day_idx in range(1, min(8, len(row))):
                if (row[day_idx] or "").strip():
                    day_hours[day_idx - 1] += slot_hours
        weekly_total = sum(day_hours)
        items = [f"{day_names[i]}: {day_hours[i]:.1f} h" for i in range(7)]
        items.append(f"TOTAL SEMANA: {weekly_total:.1f} h")
        return items

    def _build_group_hours_summary_items(self, schedule_rows: list[list[str]]) -> list[str]:
        day_names = HEADER_NAMES[1:]
        day_hours = [0.0] * 7
        for row in schedule_rows:
            slot_hours = self._slot_hours(row[0] if row else "")
            for day_idx in range(1, min(8, len(row))):
                if (row[day_idx] or "").strip():
                    day_hours[day_idx - 1] += slot_hours
        weekly_total = sum(day_hours)
        items = [f"{day_names[i]}: {day_hours[i]:.1f} h" for i in range(7)]
        items.append(f"TOTAL GRUPO: {weekly_total:.1f} h")
        return items

    def _build_teacher_groups_summary_items(self, teacher_key: str) -> list[str]:
        by_group = self._teacher_group_hours.get(teacher_key, {})
        if not by_group:
            return ["GRUPOS: sin datos"]
        return [f"{group}: {hours:.1f} h" for group, hours in sorted(by_group.items())]

    def _set_summary_chips(self, items: list[str]) -> None:
        while self.summary_layout.count():
            item = self.summary_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for text in items:
            chip = QLabel(text)
            chip.setProperty("role", "statChip")
            chip.setObjectName("HorarioChip")
            tone, tone_idx = self._chip_tone(text)
            chip.setProperty("tone", tone)
            if tone_idx:
                chip.setProperty("toneIdx", tone_idx)
            chip.setAlignment(Qt.AlignCenter)
            self.summary_layout.addWidget(chip)

    def _set_status_chips(self, items: list[str]) -> None:
        while self.status_layout.count():
            item = self.status_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if widget in {self.date_label, self.schedule_date_selector, self.export_teachers_button}:
                    continue
                widget.deleteLater()
        for text in items:
            chip = QLabel(text)
            chip.setObjectName("HorarioStatusChip")
            chip.setProperty("role", "statChip")
            if text.upper().startswith("DOCENTE:"):
                chip.setObjectName("HorarioStatusChipDocente")
            chip.setAlignment(Qt.AlignCenter)
            self.status_layout.addWidget(chip)
        self.status_layout.addWidget(self.export_teachers_button)
        self.status_layout.addStretch(1)
        self.status_layout.addWidget(self.date_label)
        self.status_layout.addWidget(self.schedule_date_selector)

    def _chip_tone(self, text: str) -> tuple[str, str]:
        upper = (text or "").upper()
        if upper.startswith("TOTAL"):
            return "total", ""
        if any(upper.startswith(day) for day in HEADER_NAMES[1:]):
            return "day", ""
        idx = self._group_color_index(text)
        return "group", str(idx)

    def _group_color_index(self, text: str) -> int:
        key = (text or "").split(":", 1)[0].strip().upper()
        if not key:
            return 0
        return sum(ord(ch) for ch in key) % 8
