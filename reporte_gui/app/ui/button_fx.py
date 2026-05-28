from __future__ import annotations

from PySide6.QtCore import QObject, QEvent, QEasingCurve, QPropertyAnimation, QAbstractAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton, QGraphicsDropShadowEffect
from shiboken6 import isValid


class GlobalButton3DAnimator(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._effects: dict[QPushButton, QGraphicsDropShadowEffect] = {}

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        try:
            if isinstance(watched, QPushButton):
                self._ensure_effect(watched)
                if watched in self._effects:
                    if event.type() == QEvent.Enter:
                        self._animate(watched, blur=16.0, y_offset=6.0, alpha=150)
                    elif event.type() == QEvent.Leave:
                        self._animate(watched, blur=10.0, y_offset=3.0, alpha=110)
                    elif event.type() == QEvent.MouseButtonPress:
                        self._animate(watched, blur=6.0, y_offset=1.0, alpha=95)
                    elif event.type() == QEvent.MouseButtonRelease:
                        if watched.underMouse():
                            self._animate(watched, blur=16.0, y_offset=6.0, alpha=150)
                        else:
                            self._animate(watched, blur=10.0, y_offset=3.0, alpha=110)
        except Exception:
            # Nunca bloquear el loop UI por efectos visuales.
            return False
        return super().eventFilter(watched, event)

    def _ensure_effect(self, button: QPushButton) -> None:
        if button in self._effects:
            return
        if not isValid(button):
            return
        # Evita aplicar sobre objetos en destrucción o no inicializados.
        if button.parent() is None:
            return
        try:
            effect = QGraphicsDropShadowEffect(button)
            effect.setBlurRadius(10.0)
            effect.setOffset(0.0, 3.0)
            effect.setColor(QColor(0, 0, 0, 110))
            button.setGraphicsEffect(effect)
            self._effects[button] = effect
            button.destroyed.connect(lambda *_: self._effects.pop(button, None))
        except Exception:
            return

    def _animate(self, button: QPushButton, blur: float, y_offset: float, alpha: int) -> None:
        effect = self._effects.get(button)
        if effect is None:
            return
        if not isValid(button):
            self._effects.pop(button, None)
            return

        anim_blur = QPropertyAnimation(effect, b"blurRadius", self)
        anim_blur.setDuration(130)
        anim_blur.setEasingCurve(QEasingCurve.OutCubic)
        anim_blur.setStartValue(effect.blurRadius())
        anim_blur.setEndValue(blur)
        anim_blur.start(QAbstractAnimation.DeleteWhenStopped)

        anim_offset = QPropertyAnimation(effect, b"yOffset", self)
        anim_offset.setDuration(130)
        anim_offset.setEasingCurve(QEasingCurve.OutCubic)
        anim_offset.setStartValue(effect.yOffset())
        anim_offset.setEndValue(y_offset)
        anim_offset.start(QAbstractAnimation.DeleteWhenStopped)

        effect.setColor(QColor(0, 0, 0, max(0, min(255, alpha))))
