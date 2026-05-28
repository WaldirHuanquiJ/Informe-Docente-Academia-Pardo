from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QEasingCurve, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPalette
from PySide6.QtWidgets import QWidget


class CircularProgress(QWidget):
    def __init__(self, title: str, color: str = "#4fb3ff") -> None:
        super().__init__()
        self._value = 0.0
        self._target = 0
        self._title = title
        self._color = QColor(color)
        self.setMinimumSize(150, 150)
        self.setMaximumSize(190, 190)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(700)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._on_animated_value)

    def _on_animated_value(self, value) -> None:
        self._value = float(value)
        self.update()

    def set_value(self, value: int) -> None:
        clamped = max(0, min(100, int(value)))
        self._target = clamped
        self._animation.stop()
        self._animation.setStartValue(self._value)
        self._animation.setEndValue(float(clamped))
        self._animation.start()

    def paintEvent(self, event) -> None:  # noqa: N802
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        is_light = self.palette().color(QPalette.Window).lightness() > 160
        if is_light:
            shadow_color = QColor(15, 23, 42, 30)
            base_color = QColor("#d7e2f1")
            track_color = QColor("#e7eef8")
            percent_color = QColor("#0f172a")
            title_color = QColor("#5b6b82")
            glow_alpha = 58
        else:
            shadow_color = QColor(0, 0, 0, 85)
            base_color = QColor("#1a2a40")
            track_color = QColor("#1e3050")
            percent_color = QColor("#ffffff")
            title_color = QColor("#8899b0")
            glow_alpha = 80

        side = min(self.width(), self.height() - 36)
        x = (self.width() - side) / 2
        y = 10
        arc_rect = QRectF(x, y, side, side)
        inner_rect = arc_rect.adjusted(8, 8, -8, -8)

        # Sombra exterior sutil para volumen.
        shadow_pen = QPen(shadow_color, 8)
        painter.setPen(shadow_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(arc_rect.adjusted(2, 4, 2, 4), 0, 360 * 16)

        # Capa de base sutil (glass).
        base_pen = QPen(base_color, 5)
        painter.setPen(base_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(arc_rect, 0, 360 * 16)

        track_pen = QPen(track_color, 13)
        painter.setPen(track_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(inner_rect, 0, 360 * 16)

        # Progreso principal con glow.
        glow = QPen(QColor(self._color.darker(180)), 16)
        glow.setColor(QColor(self._color.red(), self._color.green(), self._color.blue(), glow_alpha))
        painter.setPen(glow)
        span = int(360 * self._value / 100)
        painter.drawArc(inner_rect, 90 * 16, -span * 16)

        progress_pen = QPen(self._color, 13)
        painter.setPen(progress_pen)
        painter.drawArc(inner_rect, 90 * 16, -span * 16)

        percent_font = QFont("Segoe UI Semibold", 17)
        percent_font.setBold(True)
        painter.setFont(percent_font)
        painter.setPen(percent_color)
        painter.drawText(inner_rect, Qt.AlignCenter, f"{int(round(self._value))}%")

        title_font = QFont("Segoe UI", 9)
        title_font.setWeight(QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(title_color)
        painter.drawText(self.rect().adjusted(0, 0, 0, 2), Qt.AlignBottom | Qt.AlignHCenter, self._title)
