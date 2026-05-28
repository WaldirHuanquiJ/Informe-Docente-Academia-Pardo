from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget
from app.ui.window_theme import schedule_title_bar_theme


class HelpDialog(QDialog):
    def __init__(self, parent=None, theme_mode: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ayuda")
        self.setModal(True)
        self.resize(760, 620)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        if theme_mode in {"light", "dark"}:
            self._is_light = theme_mode == "light"
        else:
            self._is_light = self.palette().color(QPalette.Window).lightness() > 160
        self._apply_theme_qss()
        self._build_ui()
        schedule_title_bar_theme(self, is_light=self._is_light)

    def _apply_theme_qss(self) -> None:
        if self._is_light:
            bg, card, text, muted, accent = "#f8fafc", "#ffffff", "#0f172a", "#475569", "#1d4ed8"
            border, btn_bg, btn_hover = "#d7dfec", "#1d4ed8", "#1e40af"
        else:
            bg, card, text, muted, accent = "#111827", "#0f172a", "#f8fafc", "#cbd5e1", "#38bdf8"
            border, btn_bg, btn_hover = "#334155", "#38bdf8", "#0ea5e9"

        self.setStyleSheet(
            f"""
            QDialog {{ background: {bg}; color: {text}; font-family: "Segoe UI"; font-size: 12px; }}
            QScrollArea {{ border: none; background: transparent; }}
            QWidget#HelpCard {{ background: {card}; border: 1px solid {border}; border-radius: 12px; }}
            QLabel#HelpTitle {{ color: {text}; font-size: 24px; font-weight: 900; }}
            QLabel#HelpSubtitle {{ color: {muted}; font-size: 12px; }}
            QLabel#HelpSection {{ color: {accent}; font-size: 11px; font-weight: 900; padding-top: 8px; }}
            QLabel#HelpBody {{ color: {muted}; font-size: 12px; }}
            QPushButton#HelpClose {{
                background: {btn_bg}; color: #ffffff; border: none; border-radius: 8px;
                padding: 8px 16px; font-weight: 800;
            }}
            QPushButton#HelpClose:hover {{ background: {btn_hover}; }}
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, 1)

        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)

        card = QWidget()
        card.setObjectName("HelpCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(8)
        content_layout.addWidget(card)

        title = QLabel("Centro de Ayuda")
        title.setObjectName("HelpTitle")
        subtitle = QLabel("Guia completa de uso del sistema de Reporte Docente.")
        subtitle.setObjectName("HelpSubtitle")
        subtitle.setWordWrap(True)
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)

        sections = [
            (
                "1. FLUJO RECOMENDADO",
                "1) Horario: importar o recargar HORARIO_YYYYMMDD.xlsx.\n"
                "2) Reporte de Asistencia: importar XLS biometrico.\n"
                "3) Dashboard: validar indicadores y progreso por docente.\n"
                "4) Informe: exportar PDF individual o masivo.",
            ),
            (
                "2. MODULO HORARIO",
                "- Carga la estructura base de bloques y docentes.\n"
                "- Si actualizas un HORARIO_YYYYMMDD.xlsx, usa recargar.\n"
                "- Si no ves docentes, valida nombres/departamentos.",
            ),
            (
                "3. MODULO REPORTE DE ASISTENCIA",
                "- Importa el XLS biometrico desde el boton correspondiente.\n"
                "- Los colores de celdas indican estado (puntual/tardanza/falta).\n"
                "- Usa filtros por nombre y departamento para revision rapida.",
            ),
            (
                "4. DASHBOARD",
                "- Muestra metricas globales y detalle por docente.\n"
                "- Los circulos animados indican porcentajes de rendimiento.\n"
                "- Puedes revisar rendimiento por semana y por dia.",
            ),
            (
                "5. INFORME Y EXPORTACION",
                "- Exportar PDF: genera informe individual del docente seleccionado.\n"
                "- Exportar todos: genera informes de docentes que si figuran en horario.\n"
                "- El sistema solicita carpeta de destino para lote.",
            ),
            (
                "6. IMPRESION",
                "- Imprimir: salida directa a la impresora seleccionada (sin abrir Adobe).\n"
                "- Imprimir todos: imprime los informes en lote.\n"
                "- Si tu impresora soporta duplex, selecciona doble faz en opciones.",
            ),
            (
                "7. CONFIGURACION",
                "- Desde Configuracion puedes cambiar tema (Oscuro/Claro).\n"
                "- Ajusta rutas de datos, exportaciones y spool de impresion.\n"
                "- La impresora elegida se guarda para siguientes sesiones.",
            ),
            (
                "8. SOLUCION DE PROBLEMAS",
                "- No aparecen datos: revisa que horario y reporte sean del mismo periodo.\n"
                "- Impresion en blanco: valida driver y modo color/escala en opciones.\n"
                "- Error PySide6 en VS Code: verifica interpreter del venv y reinicia editor.",
            ),
            (
                "9. BUENAS PRACTICAS",
                "- Mantener nombres de docentes consistentes entre fuentes.\n"
                "- Usar carpeta de exportacion dedicada por fecha/corte.\n"
                "- Probar una impresion individual antes de lote masivo.",
            ),
        ]

        for section_title, body_text in sections:
            sec = QLabel(section_title)
            sec.setObjectName("HelpSection")
            body = QLabel(body_text)
            body.setObjectName("HelpBody")
            body.setWordWrap(True)
            card_layout.addWidget(sec)
            card_layout.addWidget(body)

        close_btn = QPushButton("Cerrar")
        close_btn.setObjectName("HelpClose")
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)
