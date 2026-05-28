from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHeaderView, QTableWidgetItem

from app.services.schedule_utils import HEADER_NAMES, TIME_SLOTS, extract_schedule_blocks_with_continuity


def render_selected_sheet(view) -> None:
    if not view._workbook:
        return

    idx = view.sheet_selector.currentIndex()
    if idx < 0 or idx >= len(view._sheet_views):
        return

    sheet_idx, variant = view._sheet_views[idx]
    sheet = view._workbook.sheets[sheet_idx]
    view_name = view._sheet_view_name(sheet.name, variant)
    blocks = extract_schedule_blocks_with_continuity(sheet.rows)
    projected_blocks = [(hdr, view._project_schedule_rows(rows, variant)) for hdr, rows in blocks]
    view._sync_block_selector(projected_blocks)

    block_idx = view.block_selector.currentIndex()
    if block_idx < 0:
        block_idx = 0

    headers, schedule_rows = (
        projected_blocks[block_idx] if projected_blocks else (HEADER_NAMES, [[""] * 8 for _ in TIME_SLOTS])
    )

    selected_teacher = view._selected_teacher_key()
    if selected_teacher:
        teacher_obj = view._teacher_by_key.get(selected_teacher)
        headers, schedule_rows = view._render_teacher_merged(selected_teacher)
        total_hours = view._teacher_global_hours.get(selected_teacher, 0.0)
        display_name = teacher_obj.name if teacher_obj else selected_teacher
        view._set_status_chips(
            [
                f"Docente: {display_name.upper()}",
                f"Total de horas: {total_hours:.1f} h",
                "Cruces: celdas con varias entradas",
            ]
        )
        items = view._build_daily_hours_summary_items(schedule_rows)
        items.extend(view._build_teacher_groups_summary_items(selected_teacher))
        view._set_summary_chips(items)
    else:
        view._set_status_chips([f"Mostrando: {view_name}", f"Turnos: {len(projected_blocks)}"])
        view._set_summary_chips(view._build_group_hours_summary_items(schedule_rows))

    visible_cols = min(7, max(0, len(headers) - 1))
    view.table.setColumnCount(visible_cols)
    view.table.setHorizontalHeaderLabels(headers[1 : 1 + visible_cols])
    view.table.setRowCount(len(schedule_rows))
    view.table.setVerticalHeaderLabels([(row[0] if row else "") for row in schedule_rows])

    bold_font = QFont()
    bold_font.setBold(True)

    for r, row in enumerate(schedule_rows):
        for c, value in enumerate(row[1 : 1 + visible_cols]):
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignCenter)
            view.table.setItem(r, c, item)

    view.table.verticalHeader().setFont(bold_font)

    view.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    viewport_width = max(view.table.viewport().width(), 1)
    equal_width = max(150, (viewport_width // max(1, visible_cols)) - 2)
    for c in range(visible_cols):
        view.table.setColumnWidth(c, equal_width)

    view.table.verticalHeader().setDefaultSectionSize(52)
    view.table.resizeRowsToContents()


def sync_block_selector(view, blocks: list[tuple[list[str], list[list[str]]]]) -> None:
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

    current = view.block_selector.currentText()
    view.block_selector.blockSignals(True)
    view.block_selector.clear()
    view.block_selector.addItems(labels or ["Turno"])
    if current in labels:
        view.block_selector.setCurrentIndex(labels.index(current))
    else:
        view.block_selector.setCurrentIndex(0)
    view.block_selector.blockSignals(False)
