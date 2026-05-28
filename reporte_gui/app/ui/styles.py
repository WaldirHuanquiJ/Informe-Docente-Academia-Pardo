from __future__ import annotations

DARK_THEME = """
/* ═══════════════════════════════════════════════════════════════════════════
   REPORTE DOCENTE — Tema Ultra-Moderno "Glass & Neon"
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Base global ────────────────────────────────────────────────────────── */
QWidget {
    background: #080c14;
    color: #e4eaf2;
    font-size: 12.5px;
    font-family: "Segoe UI", "Inter", "SF Pro Display", sans-serif;
}

QLabel {
    background: transparent;
    border: none;
}

/* ── Pestañas estilo navegador ──────────────────────────────────────────── */
QTabWidget::pane {
    border: none;
    border-radius: 0px;
    background: #0b1020;
    top: 0px;
    padding: 4px 0px 0px 0px;
}

QTabWidget::tab-bar {
    left: 12px;
    alignment: left;
}

QTabBar {
    background: transparent;
    border: none;
}

QTabBar::tab {
    background: transparent;
    color: #6b7d95;
    padding: 10px 22px;
    border: none;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 2px;
    margin-top: 6px;
    margin-bottom: 0px;
    font-weight: 600;
    font-size: 13px;
    min-width: 100px;
}

QTabBar::tab:!selected {
    margin-top: 8px;
    border-bottom: 2px solid transparent;
}

QTabBar::tab:hover:!selected {
    color: #9fb3cc;
    background: rgba(255, 255, 255, 0.03);
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}

QTabBar::tab:selected {
    color: #ffffff;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #131d33,
        stop:0.4 #0f172a,
        stop:1 #0b1020);
    font-weight: 700;
    border: 1px solid #1e3250;
    border-bottom: 2px solid #0b1020;
    padding: 11px 22px 12px 22px;
    margin-top: 3px;
    margin-bottom: -1px;
}

QTabBar::tab:selected::after {
    /* Línea de acento inferior tipo navegador */
}

QTabBar::scroller {
    width: 0px;
}

/* ── Toolbar superior ───────────────────────────────────────────────────── */
QWidget#toolbar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #111c32, stop:0.5 #0e1628, stop:1 #0a1020);
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    padding: 4px 0px;
}

/* ── Inputs y Combos ────────────────────────────────────────────────────── */
QLineEdit, QComboBox {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 9px 14px;
    color: #eef2f8;
    selection-background-color: #00a6ff;
    font-size: 12.5px;
}
QLineEdit:focus {
    border: 1px solid #00b4d8;
    background: rgba(0, 180, 216, 0.06);
}
QComboBox:focus {
    border: 1px solid #00b4d8;
}
QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QComboBox QAbstractItemView {
    background: #111a2e;
    border: 1px solid #1e3250;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: #00a6ff;
    outline: none;
}
QComboBox QAbstractItemView::item {
    padding: 8px 12px;
    border-radius: 6px;
}

QDoubleSpinBox {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 8px 10px;
    color: #e8f0f8;
    selection-background-color: #00a6ff;
    font-size: 13.5px;
    font-weight: 700;
}
QDoubleSpinBox:focus {
    border: 1px solid #00b4d8;
}

QSpinBox#CalendarioSpin {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255,255,255,0.08), stop:1 rgba(255,255,255,0.03));
    border: 1px solid rgba(56, 189, 248, 0.45);
    border-radius: 13px;
    padding: 7px 34px 7px 12px;
    color: #eaf3ff;
    font-size: 12.5px;
    font-weight: 800;
    min-height: 24px;
}
QSpinBox#CalendarioSpin:hover {
    border: 1px solid rgba(56, 189, 248, 0.7);
    background: rgba(56, 189, 248, 0.08);
}
QSpinBox#CalendarioSpin:focus {
    border: 1px solid #22d3ee;
    background: rgba(34, 211, 238, 0.10);
}
QSpinBox#CalendarioSpin::up-button, QSpinBox#CalendarioSpin::down-button {
    width: 20px;
    border: none;
    background: rgba(255,255,255,0.05);
    margin: 2px;
    border-radius: 8px;
}
QSpinBox#CalendarioSpin::up-button:hover, QSpinBox#CalendarioSpin::down-button:hover {
    background: rgba(56, 189, 248, 0.22);
}
QSpinBox#CalendarioSpin::up-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 6px solid #93c5fd;
}
QSpinBox#CalendarioSpin::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #93c5fd;
}

/* ── Botones ────────────────────────────────────────────────────────────── */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2563eb, stop:1 #1d4ed8);
    border: 1px solid #3b82f6;
    border-radius: 20px;
    padding: 9px 18px;
    color: #ffffff;
    font-weight: 700;
    font-size: 12.5px;
    letter-spacing: 0.2px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #3b82f6, stop:1 #2563eb);
    border: 1px solid #60a5fa;
}
QPushButton:pressed {
    background: #1e40af;
    border: 1px solid #1d4ed8;
}
QPushButton:disabled {
    background: #1a2640;
    border: 1px solid #253550;
    color: #5a6e8a;
}

/* Botón de importar (acento verde) */
QPushButton#actionImport {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #059669, stop:1 #047857);
    border: 1px solid #10b981;
}
QPushButton#actionImport:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #10b981, stop:1 #059669);
}

/* Botón limpiar (acento ámbar) */
QPushButton#actionClear {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #d97706, stop:1 #b45309);
    border: 1px solid #f59e0b;
}
QPushButton#actionClear:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #f59e0b, stop:1 #d97706);
}

/* Botón exportar (acento violeta) */
QPushButton#actionExport {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7c3aed, stop:1 #6d28d9);
    border: 1px solid #8b5cf6;
}
QPushButton#actionExport:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #8b5cf6, stop:1 #7c3aed);
}

/* Botones auxiliares de informe */
QPushButton#actionExportAll,
QPushButton#actionPrint,
QPushButton#actionPrintAll {
    border-radius: 20px;
}

/* ── Tablas ─────────────────────────────────────────────────────────────── */
QTableWidget {
    background: rgba(10, 16, 30, 0.6);
    alternate-background-color: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 16px;
    gridline-color: rgba(255, 255, 255, 0.04);
    selection-background-color: rgba(0, 166, 255, 0.25);
    selection-color: #ffffff;
    padding: 2px;
}
QTableWidget::item {
    border-bottom: 1px solid rgba(255, 255, 255, 0.03);
    padding: 8px 10px;
}
QTableWidget::item:hover {
    background: rgba(0, 180, 216, 0.08);
}
QTableWidget::item:selected {
    background: rgba(0, 166, 255, 0.30);
    color: #ffffff;
    border-bottom: 1px solid rgba(0, 166, 255, 0.15);
}

QHeaderView::section {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #162240, stop:1 #101b30);
    color: #c8d6e5;
    padding: 10px 8px;
    border: none;
    border-right: 1px solid rgba(255, 255, 255, 0.06);
    border-bottom: 1px solid rgba(0, 180, 216, 0.20);
    font-weight: 700;
    font-size: 11.5px;
    letter-spacing: 0.4px;
    text-transform: uppercase;
}
QTableCornerButton::section {
    background: transparent;
    border: none;
}

/* ── Scrollbars minimalistas ────────────────────────────────────────────── */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.10);
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(0, 180, 216, 0.35);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: rgba(255, 255, 255, 0.10);
    border-radius: 4px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover {
    background: rgba(0, 180, 216, 0.35);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* ── Hero section ───────────────────────────────────────────────────────── */
QWidget[role="hero"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(37, 99, 235, 0.25),
        stop:0.5 rgba(124, 58, 237, 0.18),
        stop:1 rgba(0, 180, 216, 0.20));
    border: 1px solid rgba(99, 102, 241, 0.25);
    border-radius: 14px;
}
QLabel[role="heroTitle"] {
    color: #ffffff;
    font-size: 24px;
    font-weight: 900;
    letter-spacing: 0.8px;
}
QLabel[role="heroSubtitle"] {
    color: #a5b4fc;
    font-size: 13px;
    font-weight: 600;
}

/* ── Cards (KPI) ────────────────────────────────────────────────────────── */
QWidget[role="card"] {
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.10);
    background: rgba(255, 255, 255, 0.03);
}

QWidget[role="card"][tone="0"] {
    border: 1px solid rgba(6, 182, 212, 0.35);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(6, 182, 212, 0.22),
        stop:0.5 rgba(14, 165, 233, 0.12),
        stop:1 rgba(6, 182, 212, 0.06));
}
QWidget[role="card"][tone="1"] {
    border: 1px solid rgba(16, 185, 129, 0.35);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(16, 185, 129, 0.22),
        stop:0.5 rgba(5, 150, 105, 0.12),
        stop:1 rgba(16, 185, 129, 0.06));
}
QWidget[role="card"][tone="2"] {
    border: 1px solid rgba(245, 158, 11, 0.35);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(245, 158, 11, 0.22),
        stop:0.5 rgba(217, 119, 6, 0.12),
        stop:1 rgba(245, 158, 11, 0.06));
}
QWidget[role="card"][tone="3"] {
    border: 1px solid rgba(236, 72, 153, 0.35);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(236, 72, 153, 0.22),
        stop:0.5 rgba(219, 39, 119, 0.12),
        stop:1 rgba(236, 72, 153, 0.06));
}
QWidget[role="card"][tone="4"] {
    border: 1px solid rgba(249, 115, 22, 0.35);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(249, 115, 22, 0.22),
        stop:0.5 rgba(234, 88, 12, 0.12),
        stop:1 rgba(249, 115, 22, 0.06));
}
QWidget[role="card"][tone="5"] {
    border: 1px solid rgba(139, 92, 246, 0.35);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(139, 92, 246, 0.22),
        stop:0.5 rgba(124, 58, 237, 0.12),
        stop:1 rgba(139, 92, 246, 0.06));
}

QLabel[role="cardTitle"] {
    background: transparent;
    border: none;
    color: rgba(255, 255, 255, 0.75);
    font-size: 11.5px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
QLabel[role="cardValue"] {
    background: transparent;
    border: none;
    color: #ffffff;
    font-size: 34px;
    font-weight: 900;
}

/* ── Paneles ────────────────────────────────────────────────────────────── */
QWidget[role="panel"] {
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 16px;
}
QLabel[role="panelTitle"] {
    color: #9ca3af;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    text-transform: uppercase;
}

/* ── Horario ────────────────────────────────────────────────────────────── */
#HorarioSummary {
    background: transparent;
    border: none;
}
#HorarioStatusHost {
    background: transparent;
    border: none;
}
#HorarioStatusChip {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 10px;
    color: #cbd5e1;
    font-size: 11px;
    font-weight: 700;
    padding: 5px 12px;
}
#HorarioStatusChipDocente {
    background: rgba(0, 180, 216, 0.15);
    border: 1px solid rgba(0, 180, 216, 0.45);
    border-radius: 10px;
    color: #e0f2fe;
    font-size: 12px;
    font-weight: 800;
    padding: 5px 12px;
}
#HorarioStatusChipOk {
    background: rgba(16, 185, 129, 0.16);
    border: 1px solid rgba(16, 185, 129, 0.45);
    border-radius: 10px;
    color: #a7f3d0;
    font-size: 11px;
    font-weight: 800;
    padding: 5px 12px;
}
#HorarioStatusChipBad {
    background: rgba(239, 68, 68, 0.16);
    border: 1px solid rgba(239, 68, 68, 0.45);
    border-radius: 10px;
    color: #fecaca;
    font-size: 11px;
    font-weight: 800;
    padding: 5px 12px;
}
#HorarioDatePicker {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(56, 189, 248, 0.45);
    border-radius: 11px;
    color: #e2e8f0;
    font-size: 11.5px;
    font-weight: 800;
    padding: 4px 10px;
    min-height: 26px;
}
#HorarioDatePicker:hover {
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(34, 211, 238, 0.75);
}
#HorarioDatePicker:focus {
    border: 1px solid rgba(34, 211, 238, 0.95);
}
#HorarioDatePicker::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: right;
    width: 20px;
    border-left: 1px solid rgba(148, 163, 184, 0.35);
}
#HorarioDatePicker::down-arrow {
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #67e8f9;
}
QGroupBox#CalendarioSuspGroup {
    border: 1px solid rgba(148, 163, 184, 0.28);
    border-radius: 14px;
    margin-top: 10px;
    padding-top: 10px;
    background: rgba(255, 255, 255, 0.02);
}
QGroupBox#CalendarioSuspGroup::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 1px 8px;
    color: #cbd5e1;
    font-weight: 800;
}
QLineEdit#CalendarioField, QComboBox#CalendarioField {
    border-radius: 11px;
    padding: 7px 11px;
}
QTimeEdit#CalendarioTime {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(148, 163, 184, 0.30);
    border-radius: 11px;
    padding: 6px 10px;
    color: #e2e8f0;
    font-weight: 800;
    min-height: 22px;
}
QTimeEdit#CalendarioTime:focus {
    border: 1px solid #22d3ee;
    background: rgba(34, 211, 238, 0.10);
}
QTableWidget#CalendarioSuspTable {
    border: 1px solid rgba(148, 163, 184, 0.30);
    border-radius: 12px;
}
QTableWidget#CalendarioSuspTable::item {
    padding: 7px 9px;
}
#HorarioCalendarPopup QWidget {
    background: #0f172a;
    color: #e2e8f0;
}
#HorarioCalendarPopup QToolButton {
    color: #e2e8f0;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(148, 163, 184, 0.28);
    border-radius: 8px;
    padding: 4px 8px;
    font-weight: 700;
}
#HorarioCalendarPopup QToolButton:hover {
    background: rgba(56, 189, 248, 0.18);
    border-color: rgba(34, 211, 238, 0.6);
}
#HorarioCalendarPopup QSpinBox {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 7px;
    color: #e2e8f0;
    padding: 3px 6px;
}
#HorarioCalendarPopup QAbstractItemView:enabled {
    background: #0b1324;
    color: #dbeafe;
    selection-background-color: rgba(34, 211, 238, 0.35);
    selection-color: #ffffff;
}
#HorarioCalendarPopup QCalendarWidget QTableView {
    background: #0b1324;
    color: #dbeafe;
    gridline-color: rgba(148, 163, 184, 0.22);
    selection-background-color: rgba(34, 211, 238, 0.35);
    selection-color: #ffffff;
}
#HorarioCalendarPopup QCalendarWidget QHeaderView::section {
    background: #111c33;
    color: #93c5fd;
    border: none;
    border-bottom: 1px solid rgba(148, 163, 184, 0.28);
    padding: 6px 4px;
    font-weight: 800;
}
#HorarioCalendarPopup QWidget#qt_calendar_navigationbar {
    background: #111c33;
}
#HorarioCalendarPopup QTableView#qt_calendar_calendarview {
    background: #0b1324;
    color: #dbeafe;
    alternate-background-color: #0f1a31;
    gridline-color: rgba(148, 163, 184, 0.22);
    selection-background-color: rgba(34, 211, 238, 0.35);
    selection-color: #ffffff;
}
#HorarioCalendarPopup QTableView#qt_calendar_calendarview QHeaderView::section {
    background: #111c33;
    color: #93c5fd;
    border: none;
    border-bottom: 1px solid rgba(148, 163, 184, 0.28);
    padding: 6px 4px;
    font-weight: 800;
}
#HorarioChip {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 10px;
    color: #d1d5db;
    font-size: 10.5px;
    font-weight: 700;
    padding: 4px 10px;
    min-width: 84px;
    max-width: 150px;
}
#HorarioChip[tone="day"] {
    background: rgba(56, 189, 248, 0.15);
    border: 1px solid rgba(56, 189, 248, 0.40);
    color: #bae6fd;
}
#HorarioChip[tone="total"] {
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.40);
    color: #a7f3d0;
    font-weight: 800;
}
#HorarioChip[tone="group"] {
    background: rgba(167, 139, 250, 0.12);
    border: 1px solid rgba(167, 139, 250, 0.30);
    color: #ddd6fe;
}

#HorarioChip[tone="group"][toneIdx="0"] { background: rgba(239, 68, 68, 0.15); border-color: rgba(248, 113, 113, 0.40); color: #fecaca; }
#HorarioChip[tone="group"][toneIdx="1"] { background: rgba(251, 146, 60, 0.15); border-color: rgba(253, 186, 116, 0.40); color: #fed7aa; }
#HorarioChip[tone="group"][toneIdx="2"] { background: rgba(16, 185, 129, 0.15); border-color: rgba(52, 211, 153, 0.40); color: #a7f3d0; }
#HorarioChip[tone="group"][toneIdx="3"] { background: rgba(56, 189, 248, 0.15); border-color: rgba(125, 211, 252, 0.40); color: #bae6fd; }
#HorarioChip[tone="group"][toneIdx="4"] { background: rgba(139, 92, 246, 0.15); border-color: rgba(167, 139, 250, 0.40); color: #ddd6fe; }
#HorarioChip[tone="group"][toneIdx="5"] { background: rgba(20, 184, 166, 0.15); border-color: rgba(45, 212, 191, 0.40); color: #99f6e4; }
#HorarioChip[tone="group"][toneIdx="6"] { background: rgba(250, 204, 21, 0.15); border-color: rgba(253, 224, 71, 0.45); color: #fef08a; }
#HorarioChip[tone="group"][toneIdx="7"] { background: rgba(251, 146, 60, 0.15); border-color: rgba(253, 186, 116, 0.40); color: #fed7aa; }

#HorarioTable {
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 14px;
    background: rgba(10, 16, 30, 0.5);
    gridline-color: rgba(255, 255, 255, 0.04);
}
#HorarioTable::item {
    padding: 8px 8px;
}
#HorarioTable QHeaderView::section {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #152040, stop:1 #0e182a);
    color: #c8d6e5;
    font-size: 11.5px;
    font-weight: 800;
    border: none;
    border-right: 1px solid rgba(255, 255, 255, 0.06);
    border-bottom: 1px solid rgba(0, 180, 216, 0.20);
    padding: 10px 6px;
    letter-spacing: 0.5px;
}

/* ── Nombre del docente ─────────────────────────────────────────────────── */
QLabel[role="teacherName"] {
    color: #ffffff;
    font-size: 21px;
    font-weight: 900;
    letter-spacing: 0.6px;
    padding: 2px 0px 2px 2px;
}

/* ── Chips de estadísticas ──────────────────────────────────────────────── */
QLabel[role="statChip"] {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    color: #d1d5db;
    font-size: 11.5px;
    font-weight: 700;
    padding: 6px 12px;
}

/* ── ProgressBar ────────────────────────────────────────────────────────── */
QProgressBar {
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    background: rgba(0, 0, 0, 0.25);
    text-align: center;
    font-weight: 700;
    min-height: 20px;
    color: #ffffff;
}
QProgressBar::chunk {
    border-radius: 9px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #06b6d4, stop:0.5 #0ea5e9, stop:1 #6366f1);
}
QProgressBar#slotProgressThin {
    min-height: 12px;
    max-height: 14px;
    border-radius: 7px;
    font-size: 10px;
    font-weight: 700;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(148, 163, 184, 0.35);
    color: #e2e8f0;
}
QProgressBar#slotProgressThin::chunk {
    border-radius: 6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #22d3ee, stop:0.5 #14b8a6, stop:1 #34d399);
}

/* ── Tooltips ───────────────────────────────────────────────────────────── */
QToolTip {
    background: #0f172a;
    color: #e2e8f0;
    border: 1px solid rgba(0, 180, 216, 0.35);
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 11.5px;
}

/* ── Info label (estado de compatibilidad) ──────────────────────────────── */
QLabel#infoLabel {
    padding: 8px 14px;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    font-size: 13px;
    font-weight: 600;
}
QLabel[role="muted"] { color: #8da0bc; }
QDoubleSpinBox#weekHoursInput {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(140,185,230,0.45);
    border-radius: 10px;
    padding: 5px 10px;
    font-weight: 700;
}
"""


LIGHT_THEME = """
QWidget {
    background: #f5f7fb;
    color: #1f2937;
    font-size: 12.5px;
    font-family: "Segoe UI", "Inter", "SF Pro Display", sans-serif;
}
QLabel { background: transparent; border: none; color: #1f2937; }

QTabWidget::pane {
    border: 1px solid #d7deea;
    border-radius: 10px;
    background: #ffffff;
    top: 0px;
}
QTabBar::tab {
    background: #eef2f8;
    color: #475569;
    padding: 9px 18px;
    border: 1px solid #d6deea;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #1f2937;
    border: 1px solid #c8d3e4;
    font-weight: 700;
}

QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background: #ffffff;
    border: 1px solid #cfd8e6;
    border-radius: 10px;
    padding: 7px 10px;
    color: #111827;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #4f84c4;
}
QSpinBox#CalendarioSpin {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f7fbff);
    border: 1px solid #b7cdec;
    border-radius: 13px;
    padding: 7px 34px 7px 12px;
    color: #12325a;
    font-size: 12.5px;
    font-weight: 800;
    min-height: 24px;
}
QSpinBox#CalendarioSpin:hover {
    border: 1px solid #7ea9dd;
    background: #f4f9ff;
}
QSpinBox#CalendarioSpin:focus {
    border: 1px solid #3b82f6;
    background: #eef6ff;
}
QSpinBox#CalendarioSpin::up-button, QSpinBox#CalendarioSpin::down-button {
    width: 20px;
    border: none;
    background: #eef5ff;
    margin: 2px;
    border-radius: 8px;
}
QSpinBox#CalendarioSpin::up-button:hover, QSpinBox#CalendarioSpin::down-button:hover {
    background: #dbeafe;
}
QSpinBox#CalendarioSpin::up-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 6px solid #2563eb;
}
QSpinBox#CalendarioSpin::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #2563eb;
}
QComboBox {
    padding-right: 30px;
}
QComboBox:hover {
    background: #f8fbff;
    border: 1px solid #8fb3de;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: right;
    width: 24px;
    border-left: 1px solid #c7d6ea;
    background: #f4f8ff;
    border-top-right-radius: 10px;
    border-bottom-right-radius: 10px;
}
QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #2563eb;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #bfd3ec;
    border-radius: 10px;
    padding: 4px;
    selection-background-color: #dbeafe;
    selection-color: #0f172a;
    outline: none;
}
QComboBox QAbstractItemView::item {
    min-height: 24px;
    padding: 6px 10px;
    border-radius: 7px;
}
QComboBox QAbstractItemView::item:hover {
    background: #eef5ff;
}
QComboBox QAbstractItemView::item:selected {
    background: #dbeafe;
    color: #0f172a;
}
#HorarioDatePicker {
    background: #ffffff;
    border: 1px solid #b9cae3;
    border-radius: 11px;
    color: #1f2937;
    font-size: 11.5px;
    font-weight: 800;
    padding: 4px 10px;
    min-height: 26px;
}
#HorarioDatePicker:hover {
    background: #f7fbff;
    border-color: #7aa6da;
}
#HorarioDatePicker:focus {
    border: 1px solid #4f84c4;
}
#HorarioDatePicker::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: right;
    width: 20px;
    border-left: 1px solid #c7d6ea;
}
#HorarioDatePicker::down-arrow {
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #2563eb;
}
#HorarioStatusChipOk {
    background: #e9f9f1;
    border: 1px solid #b8e6cb;
    border-radius: 10px;
    color: #0f6b43;
    font-size: 11px;
    font-weight: 800;
    padding: 5px 12px;
}
#HorarioStatusChipBad {
    background: #ffeceb;
    border: 1px solid #f3c5c1;
    border-radius: 10px;
    color: #9f2f27;
    font-size: 11px;
    font-weight: 800;
    padding: 5px 12px;
}
#HorarioCalendarPopup QWidget {
    background: #ffffff;
    color: #1f2937;
}
#HorarioCalendarPopup QToolButton {
    color: #1e3a8a;
    background: #eef5ff;
    border: 1px solid #c7d8ef;
    border-radius: 8px;
    padding: 4px 8px;
    font-weight: 700;
}
#HorarioCalendarPopup QToolButton:hover {
    background: #e3efff;
    border-color: #95b7e2;
}
#HorarioCalendarPopup QSpinBox {
    background: #ffffff;
    border: 1px solid #c7d8ef;
    border-radius: 7px;
    color: #1f2937;
    padding: 3px 6px;
}
#HorarioCalendarPopup QAbstractItemView:enabled {
    background: #ffffff;
    color: #1f2937;
    selection-background-color: #dbeafe;
    selection-color: #0f172a;
}
#HorarioCalendarPopup QCalendarWidget QTableView {
    background: #ffffff;
    color: #1f2937;
    gridline-color: #d8e3f2;
    selection-background-color: #dbeafe;
    selection-color: #0f172a;
}
#HorarioCalendarPopup QCalendarWidget QHeaderView::section {
    background: #f3f7ff;
    color: #334155;
    border: none;
    border-bottom: 1px solid #d3deef;
    padding: 6px 4px;
    font-weight: 800;
}
#HorarioCalendarPopup QWidget#qt_calendar_navigationbar {
    background: #f4f8ff;
}
#HorarioCalendarPopup QTableView#qt_calendar_calendarview {
    background: #ffffff;
    color: #1f2937;
    alternate-background-color: #f8fbff;
    gridline-color: #d8e3f2;
    selection-background-color: #dbeafe;
    selection-color: #0f172a;
}
#HorarioCalendarPopup QTableView#qt_calendar_calendarview QHeaderView::section {
    background: #f3f7ff;
    color: #334155;
    border: none;
    border-bottom: 1px solid #d3deef;
    padding: 6px 4px;
    font-weight: 800;
}

QPushButton {
    background: #e8f1ff;
    border: 1px solid #c5d9f6;
    border-radius: 20px;
    padding: 8px 16px;
    color: #1e3a8a;
    font-weight: 700;
}
QPushButton:hover { background: #dceaff; }
QPushButton:pressed { background: #cfe1fb; }
QPushButton:disabled {
    background: #eef2f8;
    border: 1px solid #d9e1ec;
    color: #8a93a3;
}
QPushButton#actionImport { background: #e7f8ef; border-color: #b8e6cb; color: #0f6b43; }
QPushButton#actionImport:hover { background: #daf3e5; }
QPushButton#actionClear { background: #fff1e3; border-color: #f2d2ae; color: #9a5a08; }
QPushButton#actionClear:hover { background: #ffe8d3; }
QPushButton#actionExport { background: #efe9ff; border-color: #d5c8fb; color: #4f36a6; }
QPushButton#actionExport:hover { background: #e5dbff; }
QPushButton#actionExportAll,
QPushButton#actionPrint,
QPushButton#actionPrintAll {
    border-radius: 20px;
}

QTableWidget {
    background: #ffffff;
    alternate-background-color: #f8fbff;
    border: 1px solid #d3dceb;
    border-radius: 12px;
    gridline-color: #e7edf6;
    selection-background-color: #dbeafe;
    selection-color: #0b1324;
    outline: none;
}
QTableWidget::item {
    padding: 7px 9px;
    border-bottom: 1px solid #edf2f9;
}
QTableWidget::item:hover {
    background: #eef6ff;
}
QTableWidget::item:selected {
    background: #dbeafe;
    color: #0b1324;
    border-bottom: 1px solid #c9defa;
}
QHeaderView::section {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f5f8fe, stop:1 #e9f0fb);
    color: #334155;
    padding: 9px 7px;
    border: none;
    border-right: 1px solid #d7dfec;
    border-bottom: 1px solid #cfd9e8;
    font-weight: 800;
    font-size: 11.5px;
}
QTableCornerButton::section {
    background: #eef3fb;
    border: 1px solid #d7dfec;
}
#ReporteTable {
    background: #ffffff;
    alternate-background-color: #f5f9ff;
    border: 1px solid #cfdced;
    border-radius: 12px;
    gridline-color: #dde8f5;
    selection-background-color: #dbeafe;
    selection-color: #0b1324;
}
#ReporteTable::item {
    padding: 8px 10px;
    border-bottom: 1px solid #e8eff9;
}
#ReporteTable::item:hover {
    background: #edf5ff;
}
#ReporteTable::item:selected {
    background: #dbeafe;
    color: #0b1324;
    border-bottom: 1px solid #bed5f6;
}
#ReporteTable QHeaderView::section {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f6f9ff, stop:1 #e9f1fd);
    color: #243b5a;
    padding: 10px 8px;
    border-right: 1px solid #d3deed;
    border-bottom: 1px solid #c7d6ea;
    font-weight: 900;
    font-size: 11.5px;
}
#ReporteTable QTableCornerButton::section {
    background: #edf3fc;
    border: 1px solid #d3deed;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #c7d6ea;
    border: 1px solid #b7c8e0;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #9db9de;
    border-color: #89acd8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #c7d6ea;
    border: 1px solid #b7c8e0;
    border-radius: 5px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover {
    background: #9db9de;
    border-color: #89acd8;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QLabel[role="heroTitle"] { color: #0f172a; font-size: 23px; font-weight: 900; }
QLabel[role="heroSubtitle"] { color: #475569; font-size: 12px; }
QWidget[role="card"] {
    border-radius: 16px;
    border: 1px solid #d8e1ef;
    background: #ffffff;
}
QWidget[role="card"][tone="0"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #eef6ff, stop:1 #ffffff);
    border: 1px solid #cfe0fb;
}
QWidget[role="card"][tone="1"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #eefdf6, stop:1 #ffffff);
    border: 1px solid #cbeedc;
}
QWidget[role="card"][tone="2"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #fff7ed, stop:1 #ffffff);
    border: 1px solid #f5dfbf;
}
QWidget[role="card"][tone="3"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f5f3ff, stop:1 #ffffff);
    border: 1px solid #ddd3fb;
}
QWidget[role="card"][tone="4"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #eefbfd, stop:1 #ffffff);
    border: 1px solid #cdebf0;
}
QWidget[role="card"][tone="5"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #fff1f2, stop:1 #ffffff);
    border: 1px solid #f5d1d7;
}
QLabel[role="cardTitle"] { color: #64748b; font-size: 11px; font-weight: 700; }
QLabel[role="cardValue"] { color: #0f172a; font-size: 32px; font-weight: 900; }
QWidget[role="card"][tone="0"] QLabel[role="cardValue"] { color: #1d4ed8; }
QWidget[role="card"][tone="1"] QLabel[role="cardValue"] { color: #059669; }
QWidget[role="card"][tone="2"] QLabel[role="cardValue"] { color: #c2410c; }
QWidget[role="card"][tone="3"] QLabel[role="cardValue"] { color: #6d28d9; }
QWidget[role="card"][tone="4"] QLabel[role="cardValue"] { color: #0f766e; }
QWidget[role="card"][tone="5"] QLabel[role="cardValue"] { color: #be123c; }
QLabel[role="statChip"] {
    background: #ffffff;
    border: 1px solid #d4deeb;
    border-radius: 10px;
    color: #334155;
    padding: 5px 10px;
}
/* Fila de indicadores superior (Horario / Reporte / Dashboard) */
#HorarioStatusHost {
    background: transparent;
    border: none;
}
#HorarioStatusChip {
    background: #f8fbff;
    border: 1px solid #c7d9f2;
    border-radius: 10px;
    color: #1e3a5f;
    font-size: 11px;
    font-weight: 800;
    padding: 5px 12px;
}
#HorarioStatusChipDocente {
    background: #e7f2ff;
    border: 1px solid #93c5fd;
    border-radius: 10px;
    color: #1e40af;
    font-size: 12px;
    font-weight: 900;
    padding: 5px 12px;
}
#HorarioStatusChipOk {
    background: #e9f9ef;
    border: 1px solid #86efac;
    border-radius: 10px;
    color: #166534;
    font-size: 11px;
    font-weight: 900;
    padding: 5px 12px;
}
#HorarioStatusChipBad {
    background: #fdecec;
    border: 1px solid #fca5a5;
    border-radius: 10px;
    color: #991b1b;
    font-size: 11px;
    font-weight: 900;
    padding: 5px 12px;
}
#HorarioDatePicker {
    background: #ffffff;
    border: 1px solid #93c5fd;
    border-radius: 11px;
    color: #0f172a;
    font-size: 11.5px;
    font-weight: 800;
    padding: 4px 10px;
    min-height: 26px;
}
#HorarioDatePicker:hover {
    background: #f8fbff;
    border-color: #60a5fa;
}
#HorarioDatePicker:focus {
    border: 1px solid #3b82f6;
}
#HorarioDatePicker::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: right;
    width: 20px;
    border-left: 1px solid #cbd5e1;
}
QGroupBox#CalendarioSuspGroup {
    border: 1px solid #cfdcec;
    border-radius: 14px;
    margin-top: 10px;
    padding-top: 10px;
    background: #f8fbff;
}
QGroupBox#CalendarioSuspGroup::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 1px 8px;
    color: #334155;
    font-weight: 800;
}
QLineEdit#CalendarioField, QComboBox#CalendarioField {
    border-radius: 11px;
    padding: 7px 11px;
}
QTimeEdit#CalendarioTime {
    background: #ffffff;
    border: 1px solid #bfd3ec;
    border-radius: 11px;
    padding: 6px 10px;
    color: #0f172a;
    font-weight: 800;
    min-height: 22px;
}
QTimeEdit#CalendarioTime:focus {
    border: 1px solid #3b82f6;
    background: #eef6ff;
}
QTableWidget#CalendarioSuspTable {
    border: 1px solid #cfdbeb;
    border-radius: 12px;
}
QTableWidget#CalendarioSuspTable::item {
    padding: 7px 9px;
}
QLabel#infoLabel {
    padding: 8px 14px;
    border-radius: 10px;
    background: #f8fbff;
    border: 1px solid #c7d9f2;
    font-size: 13px;
    font-weight: 700;
    color: #1e3a5f;
}
QLabel[role="muted"] { color: #64748b; }
QDoubleSpinBox#weekHoursInput {
    background: #ffffff;
    border: 1px solid #cfd8e6;
    border-radius: 10px;
    padding: 5px 10px;
    font-weight: 700;
}
"""
