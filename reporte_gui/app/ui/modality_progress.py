from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class ModalityProgressBar(QWidget):
    """Barra de progreso delgada para una modalidad/horario."""

    def __init__(self, title_text: str, progress_text: str, percent: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = QLabel(title_text)
        self.title.setProperty("role", "muted")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        safe_percent = max(0, min(percent, 100))
        self._target_percent = safe_percent
        self._anim: QPropertyAnimation | None = None
        self.bar.setValue(0)
        self.bar.setFormat(progress_text)
        self.bar.setTextVisible(True)
        self.bar.setFixedHeight(14)
        self.bar.setAlignment(Qt.AlignCenter)
        self._apply_dynamic_style(0)
        self.bar.valueChanged.connect(self._apply_dynamic_style)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addWidget(self.title)
        layout.addWidget(self.bar)
        self.setLayout(layout)
        self._animate_to_target()

    def _animate_to_target(self) -> None:
        self._anim = QPropertyAnimation(self.bar, b"value", self)
        self._anim.setDuration(1200)
        self._anim.setStartValue(0)
        self._anim.setEndValue(self._target_percent)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.start()

    def _apply_dynamic_style(self, percent: int) -> None:
        app = QApplication.instance()
        is_light = bool(app and app.palette().window().color().lightness() > 160)

        def _hex_to_rgb(h: str) -> tuple[int, int, int]:
            h = h.lstrip("#")
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

        def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
            r, g, b = rgb
            return f"#{r:02x}{g:02x}{b:02x}"

        def _mix(c1: str, c2: str, t: float) -> str:
            a = _hex_to_rgb(c1)
            b = _hex_to_rgb(c2)
            r = int(round(a[0] + (b[0] - a[0]) * t))
            g = int(round(a[1] + (b[1] - a[1]) * t))
            bch = int(round(a[2] + (b[2] - a[2]) * t))
            return _rgb_to_hex((r, g, bch))

        palettes_light = [
            (0, ("#f87171", "#ef4444", "#b91c1c")),     # rojo
            (60, ("#fb923c", "#f97316", "#c2410c")),    # naranja
            (80, ("#facc15", "#eab308", "#ca8a04")),    # amarillo
            (90, ("#60a5fa", "#3b82f6", "#2563eb")),    # azul
            (100, ("#22c55e", "#16a34a", "#15803d")),   # verde
        ]
        palettes_dark = [
            (0, ("#f87171", "#ef4444", "#dc2626")),
            (60, ("#fb923c", "#f97316", "#ea580c")),
            (80, ("#fde047", "#facc15", "#eab308")),
            (90, ("#38bdf8", "#0ea5e9", "#2563eb")),
            (100, ("#34d399", "#10b981", "#059669")),
        ]
        anchors = palettes_light if is_light else palettes_dark
        p = max(0, min(int(percent), 100))
        lower = anchors[0]
        upper = anchors[-1]
        for i in range(len(anchors) - 1):
            a = anchors[i]
            b = anchors[i + 1]
            if a[0] <= p <= b[0]:
                lower, upper = a, b
                break
        if upper[0] == lower[0]:
            t = 0.0
        else:
            t = (p - lower[0]) / float(upper[0] - lower[0])
        c0 = _mix(lower[1][0], upper[1][0], t)
        c1 = _mix(lower[1][1], upper[1][1], t)
        c2 = _mix(lower[1][2], upper[1][2], t)

        if is_light:
            bg = "#eef4fb"
            border = "#c7d6ea"
            text = "#1f2937"
        else:
            bg = "rgba(255,255,255,0.08)"
            border = "rgba(148,163,184,0.35)"
            text = "#e2e8f0"

        self.bar.setStyleSheet(
            "QProgressBar {"
            " min-height: 12px; max-height: 14px; border-radius: 7px;"
            " font-size: 10px; font-weight: 700;"
            f" background: {bg};"
            f" border: 1px solid {border};"
            f" color: {text};"
            "}"
            "QProgressBar::chunk {"
            " border-radius: 6px;"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f" stop:0 {c0}, stop:0.5 {c1}, stop:1 {c2});"
            "}"
        )
