from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)
from app.ui.window_theme import schedule_title_bar_theme


@dataclass
class PrintOptions:
    copies: int
    page_mode: str
    page_range_text: str
    orientation: str
    paper_size: str
    color_mode: str
    duplex_mode: str
    collate: bool


class PrintDialog(QDialog):
    def __init__(self, printer_names: list[str], parent=None, theme_mode: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Centro de impresion")
        self.setModal(True)
        self.setMinimumWidth(640)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self._theme_mode = theme_mode
        title_is_light = (theme_mode == "light") if theme_mode in {"light", "dark"} else (self.palette().color(QPalette.Window).lightness() > 120)
        schedule_title_bar_theme(self, is_light=title_is_light)

        self._apply_theme_qss()

        root = QVBoxLayout()
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        title = QLabel("Impresion de informes")
        title.setProperty("role", "title")
        subtitle = QLabel("Opciones de salida similares a un visor PDF profesional.")
        subtitle.setProperty("role", "subtitle")

        card = QFrame()
        card.setObjectName("card")
        grid = QGridLayout()
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self.printer_combo = QComboBox()
        self.printer_combo.addItems(printer_names)

        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 99)
        self.copies_spin.setValue(1)

        self.page_mode_combo = QComboBox()
        self.page_mode_combo.addItems(["Todo", "Pagina actual", "Rango personalizado"])
        self.page_range_input = QLineEdit()
        self.page_range_input.setPlaceholderText("Ej: 1-3,5,8")
        self.page_range_input.setEnabled(False)
        self.page_mode_combo.currentIndexChanged.connect(self._toggle_page_range)

        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Auto", "Vertical", "Horizontal"])

        self.paper_combo = QComboBox()
        self.paper_combo.addItems(["A4", "Carta", "Oficio", "A3"])

        self.color_combo = QComboBox()
        self.color_combo.addItems(["Automatico", "Blanco y negro", "Color"])

        self.duplex_combo = QComboBox()
        self.duplex_combo.addItems(["Automatico", "Simple faz", "Doble faz (largo)", "Doble faz (corto)"])
        self.duplex_combo.setCurrentIndex(2)

        self.collate_check = QCheckBox("Intercalar copias")
        self.collate_check.setChecked(True)

        grid.addWidget(QLabel("Impresora"), 0, 0)
        grid.addWidget(self.printer_combo, 0, 1, 1, 3)

        grid.addWidget(QLabel("Copias"), 1, 0)
        grid.addWidget(self.copies_spin, 1, 1)
        grid.addWidget(QLabel("Rango"), 1, 2)
        grid.addWidget(self.page_mode_combo, 1, 3)

        grid.addWidget(QLabel("Paginas"), 2, 0)
        grid.addWidget(self.page_range_input, 2, 1, 1, 3)

        grid.addWidget(QLabel("Orientacion"), 3, 0)
        grid.addWidget(self.orientation_combo, 3, 1)
        grid.addWidget(QLabel("Tamano"), 3, 2)
        grid.addWidget(self.paper_combo, 3, 3)

        grid.addWidget(QLabel("Color"), 4, 0)
        grid.addWidget(self.color_combo, 4, 1)
        grid.addWidget(QLabel("Duplex"), 4, 2)
        grid.addWidget(self.duplex_combo, 4, 3)

        grid.addWidget(self.collate_check, 5, 0, 1, 4)
        card.setLayout(grid)

        note = QLabel(
            "Nota: algunas opciones dependen del driver de la impresora y del visor PDF del sistema."
        )
        note.setProperty("role", "subtitle")

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel_button = QPushButton("Cancelar")
        cancel_button.setObjectName("secondary")
        ok_button = QPushButton("Imprimir")
        ok_button.setObjectName("primary")
        ok_button.setDefault(True)
        cancel_button.clicked.connect(self.reject)
        ok_button.clicked.connect(self.accept)
        actions.addWidget(cancel_button)
        actions.addWidget(ok_button)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addWidget(card)
        root.addWidget(note)
        root.addLayout(actions)
        self.setLayout(root)

    def _apply_theme_qss(self) -> None:
        if self._theme_mode in {"light", "dark"}:
            dark = self._theme_mode == "dark"
        else:
            dark = self.palette().color(QPalette.Window).lightness() < 120
        if dark:
            self.setStyleSheet(
                """
                QLabel[role="title"] { font-size: 20px; font-weight: 800; color: #ffffff; }
                QLabel[role="subtitle"] { color: #9fb3cc; font-size: 12px; }
                QFrame#card {
                    background: rgba(255,255,255,0.03);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 14px;
                }
                QComboBox, QLineEdit, QSpinBox {
                    background: rgba(255,255,255,0.04);
                    border: 1px solid rgba(255,255,255,0.1);
                    border-radius: 10px;
                    padding: 7px 10px;
                    min-height: 18px;
                    color: #eef2f8;
                }
                QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border: 1px solid #00b4d8; }
                QCheckBox { color: #cdd8ea; }
                QPushButton { border-radius: 16px; padding: 8px 14px; font-weight: 700; min-width: 120px; }
                QPushButton#primary {
                    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2563eb, stop:1 #1d4ed8);
                    border: 1px solid #3b82f6;
                    color: white;
                }
                QPushButton#secondary {
                    background: rgba(255,255,255,0.05);
                    border: 1px solid rgba(255,255,255,0.12);
                    color: #d8e3f4;
                }
                """
            )
            return
        self.setStyleSheet(
            """
            QLabel[role="title"] { font-size: 20px; font-weight: 800; color: #0f172a; }
            QLabel[role="subtitle"] { color: #64748b; font-size: 12px; }
            QFrame#card {
                background: #ffffff;
                border: 1px solid #d8e1ef;
                border-radius: 14px;
            }
            QComboBox, QLineEdit, QSpinBox {
                background: #ffffff;
                border: 1px solid #cfd8e6;
                border-radius: 10px;
                padding: 7px 10px;
                min-height: 18px;
                color: #0f172a;
            }
            QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border: 1px solid #4f84c4; }
            QCheckBox { color: #334155; }
            QPushButton { border-radius: 16px; padding: 8px 14px; font-weight: 700; min-width: 120px; }
            QPushButton#primary {
                background: #2f6fb2;
                border: 1px solid #2a62a2;
                color: white;
            }
            QPushButton#primary:hover { background: #3a7fc7; }
            QPushButton#secondary {
                background: #eef2f8;
                border: 1px solid #d6deea;
                color: #334155;
            }
            """
        )

    def _toggle_page_range(self) -> None:
        self.page_range_input.setEnabled(self.page_mode_combo.currentText() == "Rango personalizado")

    def selected_printer(self) -> str:
        return self.printer_combo.currentText().strip()

    def selected_options(self) -> PrintOptions:
        return PrintOptions(
            copies=int(self.copies_spin.value()),
            page_mode=self.page_mode_combo.currentText(),
            page_range_text=self.page_range_input.text().strip(),
            orientation=self.orientation_combo.currentText(),
            paper_size=self.paper_combo.currentText(),
            color_mode=self.color_combo.currentText(),
            duplex_mode=self.duplex_combo.currentText(),
            collate=bool(self.collate_check.isChecked()),
        )
