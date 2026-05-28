from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget
from app.ui.window_theme import schedule_title_bar_theme


class InfoDialog(QDialog):
    def __init__(self, parent=None, theme_mode: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Informacion del software")
        self.setModal(True)
        self.setMinimumSize(620, 500)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        if theme_mode in {"light", "dark"}:
            self._is_light = theme_mode == "light"
        else:
            self._is_light = self.palette().color(QPalette.Window).lightness() > 160
        self._apply_theme_qss()
        self._build_ui()
        schedule_title_bar_theme(self, is_light=self._is_light)

    def _apply_theme_qss(self) -> None:
        bg = "#f8fafc" if self._is_light else "#111827"
        text = "#0f172a" if self._is_light else "#f8fafc"
        muted = "#475569" if self._is_light else "#cbd5e1"
        accent = "#1d4ed8" if self._is_light else "#38bdf8"
        badge_text = "#075985" if self._is_light else "#7dd3fc"
        button_bg = "#1d4ed8" if self._is_light else "#38bdf8"
        button_hover = "#1e40af" if self._is_light else "#0ea5e9"

        self.setStyleSheet(
            f"""
            QDialog {{
                background: {bg};
                color: {text};
                font-family: "Segoe UI";
                font-size: 12px;
            }}
            QWidget#InfoCard {{
                background: transparent;
                border: none;
                border-radius: 0px;
            }}
            QLabel#InfoTitle {{
                color: {text};
                font-size: 22px;
                font-weight: 900;
            }}
            QLabel#InfoSubtitle {{
                color: {muted};
                font-size: 11px;
            }}
            QLabel#InfoBadge {{
                color: {badge_text};
                background: transparent;
                border: none;
                padding: 0;
                font-size: 10px;
                font-weight: 800;
            }}
            QLabel#InfoSection {{
                color: {accent};
                font-size: 10px;
                font-weight: 900;
                padding-top: 10px;
            }}
            QLabel#InfoBody {{
                color: {muted};
                font-size: 11px;
            }}
            QLabel#InfoAuthor {{
                color: {text};
                font-size: 13px;
                font-weight: 900;
            }}
            QPushButton#InfoCloseButton {{
                background: {button_bg};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 800;
            }}
            QPushButton#InfoCloseButton:hover {{
                background: {button_hover};
            }}
            """
        )

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(34, 28, 34, 24)
        main_layout.setSpacing(18)

        center_widget = QWidget()
        center_widget.setObjectName("InfoCard")
        center_widget.setMaximumWidth(520)
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(16, 14, 16, 14)
        center_layout.setSpacing(10)
        main_layout.addWidget(center_widget, 1, Qt.AlignmentFlag.AlignHCenter)

        logo = QLabel()
        logo.setFixedSize(136, 64)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = self._load_theme_logo()
        if not pm.isNull():
            logo.setPixmap(
                pm.scaled(
                    136,
                    64,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            logo.setText("REPORTE DOCENTE")
            logo.setObjectName("InfoAuthor")
        center_layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("REPORTE DOCENTE")
        title.setObjectName("InfoTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel(
            "Plataforma para analisis, exportacion e impresion de asistencia docente "
            "con flujo optimizado para operacion academica."
        )
        subtitle.setObjectName("InfoSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        center_layout.addWidget(title)
        center_layout.addWidget(subtitle)

        badge = QLabel(f"VERSION 1.0 | BUILD {datetime.now().strftime('%Y-%m-%d')}")
        badge.setObjectName("InfoBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(badge)

        sections = (
            (
                "AUTORIA",
                "Waldir Huanque J.",
                "Diseno, implementacion y mejora continua orientada a rendimiento y calidad de reportes.",
            ),
            (
                "OBJETIVO DEL SISTEMA",
                None,
                "Centralizar datos de horario y asistencia para generar indicadores claros y reportes "
                "con salida profesional en PDF listos para impresion.",
            ),
            (
                "CAPACIDADES PRINCIPALES",
                None,
                "1. Importacion y consolidacion de datos.\n"
                "2. Dashboard con metricas y progreso animado.\n"
                "3. Informe docente individual y exportacion masiva.\n"
                "4. Impresion directa con soporte de opciones del driver.",
            ),
            (
                "VALOR OPERATIVO",
                None,
                "Reduce tiempos de revision, mejora la consistencia del proceso y fortalece la toma "
                "de decisiones con informacion visual y estructurada.",
            ),
        )

        for section_title, author_name, body_text in sections:
            section = QLabel(section_title)
            section.setObjectName("InfoSection")
            section.setAlignment(Qt.AlignmentFlag.AlignCenter)
            center_layout.addWidget(section)

            if author_name:
                author = QLabel(author_name)
                author.setObjectName("InfoAuthor")
                author.setAlignment(Qt.AlignmentFlag.AlignCenter)
                center_layout.addWidget(author)

            body = QLabel(body_text)
            body.setObjectName("InfoBody")
            body.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body.setWordWrap(True)
            center_layout.addWidget(body)

        close_button = QPushButton("Cerrar")
        close_button.setObjectName("InfoCloseButton")
        close_button.clicked.connect(self.accept)
        center_layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignHCenter)

    def _load_theme_logo(self) -> QPixmap:
        project_root = Path(__file__).resolve().parents[3]
        logo_name = "Logo_white.png" if self._is_light else "logo_dark.png"
        logo_path = project_root / "img" / logo_name
        if logo_path.exists():
            return QPixmap(str(logo_path))
        return QPixmap()
