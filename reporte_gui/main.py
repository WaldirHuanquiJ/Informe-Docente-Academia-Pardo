from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from app.services.logging_config import setup_logging
from app.services.system_theme import is_system_dark
from app.ui.main_window import MainWindow
from app.ui.button_fx import GlobalButton3DAnimator
from app.services.app_config import load_config
from app.ui.styles import DARK_THEME, LIGHT_THEME
from app.ui.icon_factory import set_icon_theme


def _resource_path(relative: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")) / relative
    return Path(__file__).resolve().parents[1] / relative


def _resolve_effective_theme(theme_pref: str, app: QApplication) -> str:
    if theme_pref in {"light", "dark"}:
        return theme_pref
    return "dark" if is_system_dark() else "light"


def main() -> int:
    cfg = load_config()
    data_dir = Path(cfg.data_dir)
    log_dir = Path(cfg.log_dir)

    setup_logging(log_dir)

    app = QApplication(sys.argv)
    icon_path = _resource_path("img/icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    effective_theme = _resolve_effective_theme(cfg.theme, app)
    set_icon_theme(effective_theme)
    app.setStyleSheet(LIGHT_THEME if effective_theme == "light" else DARK_THEME)
    button_animator = GlobalButton3DAnimator(app)
    app.installEventFilter(button_animator)
    app.setProperty("_global_button_animator", button_animator)
    window = MainWindow(data_dir, cfg)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
