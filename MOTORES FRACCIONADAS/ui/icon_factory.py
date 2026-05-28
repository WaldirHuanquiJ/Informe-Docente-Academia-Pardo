from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication

_ICON_THEME_MODE = "auto"  # auto | light | dark


def _base_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    return pm


def set_icon_theme(mode: str) -> None:
    global _ICON_THEME_MODE
    value = (mode or "").strip().lower()
    if value in {"light", "claro", "white"}:
        _ICON_THEME_MODE = "light"
    elif value in {"dark", "oscuro"}:
        _ICON_THEME_MODE = "dark"
    else:
        _ICON_THEME_MODE = "auto"


def _is_light_theme() -> bool:
    if _ICON_THEME_MODE == "light":
        return True
    if _ICON_THEME_MODE == "dark":
        return False
    app = QApplication.instance()
    if app is None:
        return False
    return app.palette().window().color().lightness() > 160


def _draw_3d_glyph(
    painter: QPainter,
    size: int,
    symbol: str,
    *,
    top_color: QColor,
    bottom_color: QColor,
    shadow_color: QColor,
) -> None:
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    font = QFont("Segoe UI Symbol", max(11, int(size * 0.78)), QFont.Bold)
    painter.setFont(font)
    rect = QRectF(0, 0, size, size)

    # En tema claro se evita sombra para iconos mas limpios.
    if not _is_light_theme():
        painter.setPen(QPen(shadow_color, max(1.1, size * 0.09)))
        painter.drawText(rect.translated(0.0, size * 0.02), Qt.AlignCenter, symbol)

    # Relleno sólido del glifo.
    path = QPainterPath()
    baseline_y = size * 0.78
    path.addText(size * 0.12, baseline_y, font, symbol)

    painter.setBrush(bottom_color)
    painter.setPen(QPen(top_color, max(0.9, size * 0.03)))
    painter.drawPath(path)


def make_help_icon(size: int = 20) -> QIcon:
    pm = _base_pixmap(size)
    p = QPainter(pm)
    is_light = _is_light_theme()
    _draw_3d_glyph(
        p,
        size,
        "?",
        top_color=QColor("#1d4ed8") if is_light else QColor("#ffffff"),
        bottom_color=QColor("#2563eb") if is_light else QColor("#8ec5ff"),
        shadow_color=QColor(6, 14, 26, 150),
    )
    p.end()
    return QIcon(pm)


def make_info_icon(size: int = 20) -> QIcon:
    pm = _base_pixmap(size)
    p = QPainter(pm)
    is_light = _is_light_theme()
    _draw_3d_glyph(
        p,
        size,
        "i",
        top_color=QColor("#0369a1") if is_light else QColor("#ffffff"),
        bottom_color=QColor("#0284c7") if is_light else QColor("#7dd3fc"),
        shadow_color=QColor(6, 14, 26, 150),
    )
    p.end()
    return QIcon(pm)


def make_gear_icon(size: int = 20) -> QIcon:
    pm = _base_pixmap(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    cx = size / 2.0
    cy = size / 2.0
    r_outer = size * 0.38
    r_inner = size * 0.29
    tooth_h = size * 0.10
    teeth = 8

    is_light = _is_light_theme()
    ring = QColor("#3b82f6") if is_light else QColor("#ffffff")
    core = QColor("#1d4ed8") if is_light else QColor("#9fd0ff")

    # Gear ring (sin encapsulado)
    p.setBrush(ring)
    p.setPen(QPen(ring, max(1.0, size * 0.05)))
    p.drawEllipse(QRectF(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2))

    # Teeth
    p.setBrush(ring)
    p.setPen(Qt.NoPen)
    for i in range(teeth):
        a = (2 * math.pi * i) / teeth
        x1 = cx + math.cos(a) * (r_outer - size * 0.015)
        y1 = cy + math.sin(a) * (r_outer - size * 0.015)
        x2 = cx + math.cos(a) * (r_outer + tooth_h)
        y2 = cy + math.sin(a) * (r_outer + tooth_h)
        ortho = a + math.pi / 2.0
        w = size * 0.06
        pts = [
            QPointF(x1 + math.cos(ortho) * w, y1 + math.sin(ortho) * w),
            QPointF(x1 - math.cos(ortho) * w, y1 - math.sin(ortho) * w),
            QPointF(x2 - math.cos(ortho) * w, y2 - math.sin(ortho) * w),
            QPointF(x2 + math.cos(ortho) * w, y2 + math.sin(ortho) * w),
        ]
        path = QPainterPath()
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        p.drawPath(path)

    # Inner ring + hole
    p.setBrush(core)
    p.setPen(QPen(ring, max(1.0, size * 0.04)))
    p.drawEllipse(QRectF(cx - r_inner, cy - r_inner, r_inner * 2, r_inner * 2))
    r_hole = size * 0.11
    p.setBrush(Qt.transparent)
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(cx - r_hole, cy - r_hole, r_hole * 2, r_hole * 2))

    p.end()
    return QIcon(pm)


def _make_symbol_icon(symbol: str, size: int, bg: str, border: str, fg: str) -> QIcon:
    pm = _base_pixmap(size)
    p = QPainter(pm)
    is_light = _is_light_theme()
    if is_light:
        tone = QColor("#2563eb")
    else:
        fg_lower = fg.lower()
        if "ffde" in fg_lower or "ffdd" in fg_lower:
            tone = QColor("#ff8a8a")  # limpiar
        elif "ffe8" in fg_lower or "ffe7" in fg_lower:
            tone = QColor("#72f2b8")  # importar / exportar
        elif "d7ef" in fg_lower or "d8f2" in fg_lower:
            tone = QColor("#8fd9ff")  # imprimir
        else:
            tone = QColor("#8ec5ff")
    _draw_3d_glyph(
        p,
        size,
        symbol,
        top_color=QColor("#1e3a8a") if is_light else QColor("#ffffff"),
        bottom_color=tone,
        shadow_color=QColor(6, 14, 26, 150),
    )
    p.end()
    return QIcon(pm)


def make_refresh_icon(size: int = 20) -> QIcon:
    return _make_symbol_icon("↻", size, "#15263b", "#3e5f86", "#cfe5ff")


def make_import_icon(size: int = 20) -> QIcon:
    return _make_symbol_icon("↓", size, "#143326", "#2f8f67", "#c8ffe8")


def make_clear_icon(size: int = 20) -> QIcon:
    return _make_symbol_icon("✕", size, "#3a1d1d", "#9f4c4c", "#ffdede")


def make_export_icon(size: int = 20) -> QIcon:
    return _make_symbol_icon("↑", size, "#2d1f43", "#6e50a8", "#e7d9ff")


def make_export_all_icon(size: int = 20) -> QIcon:
    return _make_symbol_icon("⇪", size, "#2b2143", "#6f5aa8", "#e6dcff")


def make_print_icon(size: int = 20) -> QIcon:
    return _make_symbol_icon("⎙", size, "#1f2f3e", "#4f7fa8", "#d7efff")


def make_print_all_icon(size: int = 20) -> QIcon:
    return _make_symbol_icon("☰", size, "#1f3242", "#4f86aa", "#d8f2ff")
