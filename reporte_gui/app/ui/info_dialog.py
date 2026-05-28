from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget, QScrollArea
from app.ui.window_theme import schedule_title_bar_theme


class InfoDialog(QDialog):
    _TRUSTED_SIGNATURES = {
        "firma_white.png": {
            "size": (1536, 1024),
            "sha256": "3D0D135B3989AE774E1DE685A085E4B63CF740AC028EB98F628E52B281655E50",
        },
        "firma_dark.png": {
            "size": (1536, 1024),
            "sha256": "DAB5884717827E7A1E7CEBAF4756149A926BABC3469A9A142FEA317DEC4038DF",
        },
    }

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
        main_layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        main_layout.addWidget(scroll, 1)

        center_widget = QWidget()
        center_widget.setObjectName("InfoCard")
        center_widget.setMaximumWidth(560)
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(16, 14, 16, 14)
        center_layout.setSpacing(10)
        scroll.setWidget(center_widget)

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
                "AUTORIA Y DIRECCION TECNICA",
                "Waldir Huanque J.",
                "Diseno, arquitectura y mejora continua del sistema con enfoque en calidad operativa y trazabilidad institucional.",
            ),
            (
                "PROPOSITO INSTITUCIONAL",
                None,
                "Centralizar horarios y asistencia docente para generar indicadores confiables, dashboards ejecutivos e informes PDF listos para auditoria e impresion.",
            ),
            (
                "CAPACIDADES ESTRATEGICAS",
                None,
                "1. Importacion, validacion y consolidacion de datos.\n"
                "2. Dashboard con metricas clave y seguimiento por docente/modalidad.\n"
                "3. Reporte docente detallado con exportacion individual y masiva.\n"
                "4. Impresion directa y control de salida documental.",
            ),
            (
                "ARQUITECTURA Y TECNOLOGIAS",
                None,
                "Arquitectura modular en Python con interfaz PySide6, persistencia SQLite y motor ReportLab para reportes PDF profesionales.",
            ),
            (
                "RENDIMIENTO Y CONFIABILIDAD",
                None,
                "Procesamiento optimizado para volumen mensual, consistencia de calculo entre vistas y estabilidad para operacion continua en entorno institucional.",
            ),
            (
                "ALCANCE OPERATIVO",
                None,
                "Estandariza el control de asistencia, reduce tiempos de revision y mejora la toma de decisiones con informacion clara, consistente y verificable.",
            ),
            (
                "VERSION Y MANTENIMIENTO",
                None,
                "Version institucional con mantenimiento evolutivo, ajustes normativos y mejora permanente de experiencia de usuario y precision de metricas.",
            ),
            (
                "CONTACTO Y SOPORTE",
                None,
                "Correo: waldyhuanqui@gmail.com | cienticero1024@gmail.com\n"
                "Soporte tecnico, atencion operativa y mantenimiento del sistema.",
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

        signature = QLabel()
        signature.setAlignment(Qt.AlignmentFlag.AlignCenter)
        signature_pm = self._load_theme_signature()
        if not signature_pm.isNull():
            signature.setPixmap(
                signature_pm.scaled(
                    220,
                    78,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            center_layout.addWidget(signature, 0, Qt.AlignmentFlag.AlignHCenter)

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

    def _load_theme_signature(self) -> QPixmap:
        project_root = Path(__file__).resolve().parents[3]
        signature_name = "firma_white.png" if self._is_light else "firma_dark.png"
        signature_path = project_root / "img" / signature_name
        if signature_path.exists():
            pm = QPixmap(str(signature_path))
            if self._is_trusted_signature(signature_name, signature_path, pm):
                return pm
        return QPixmap()

    def _is_trusted_signature(self, signature_name: str, signature_path: Path, pixmap: QPixmap) -> bool:
        expected = self._TRUSTED_SIGNATURES.get(signature_name)
        if not expected or pixmap.isNull():
            return False
        if (pixmap.width(), pixmap.height()) != expected["size"]:
            return False
        digest = hashlib.sha256(signature_path.read_bytes()).hexdigest().upper()
        return digest == expected["sha256"]
