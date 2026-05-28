from __future__ import annotations

import platform
from ctypes import byref, c_int, c_void_p, sizeof, windll

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget


def apply_title_bar_theme(widget: QWidget, *, is_light: bool) -> None:
    if platform.system() != "Windows":
        return
    try:
        hwnd = int(widget.winId())
        if hwnd == 0:
            return
        value = c_int(0 if is_light else 1)
        # Windows 11/10: 20, fallback legacy: 19
        for attr in (20, 19):
            windll.dwmapi.DwmSetWindowAttribute(
                c_void_p(hwnd),
                c_int(attr),
                byref(value),
                c_int(sizeof(value)),
            )
    except Exception:
        return


def schedule_title_bar_theme(widget: QWidget, *, is_light: bool) -> None:
    apply_title_bar_theme(widget, is_light=is_light)
    QTimer.singleShot(0, lambda: apply_title_bar_theme(widget, is_light=is_light))
    QTimer.singleShot(120, lambda: apply_title_bar_theme(widget, is_light=is_light))
