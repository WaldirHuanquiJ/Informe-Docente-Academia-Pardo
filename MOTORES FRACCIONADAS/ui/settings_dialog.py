from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.app_config import AppConfig
from app.services.system_theme import is_system_dark
from app.ui.window_theme import schedule_title_bar_theme


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None, apply_callback=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuracion")
        self.setModal(True)
        self.setMinimumSize(720, 460)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        self._apply_callback = apply_callback
        self._theme_pref = config.theme if config.theme in {"light", "dark", "system"} else "system"
        self._theme = self._resolve_effective_theme(self._theme_pref)
        self._loaded_config: dict[str, object] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        title = QLabel("Configuracion esencial")
        title.setObjectName("CfgTitle")
        root.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        self.nav = QListWidget()
        self.nav.setObjectName("CfgNav")
        self.nav.setFixedWidth(190)
        for text in ("Apariencia", "Rutas"):
            self.nav.addItem(QListWidgetItem(text))
        body.addWidget(self.nav)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_apariencia(config.theme))
        self.stack.addWidget(
            self._build_rutas(
                config.data_dir,
                config.log_dir,
                config.exports_dir,
                config.print_spool_dir,
            )
        )
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.import_btn = QPushButton("Importar")
        self.export_btn = QPushButton("Exportar")
        self.apply_btn = QPushButton("Aplicar")
        self.reset_btn = QPushButton("Restaurar")
        cancel_btn = QPushButton("Cancelar")
        save_btn = QPushButton("Guardar")
        save_btn.setDefault(True)

        self.import_btn.clicked.connect(self._on_import_clicked)
        self.export_btn.clicked.connect(self._on_export_clicked)
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self.accept)

        buttons.addWidget(self.import_btn)
        buttons.addWidget(self.export_btn)
        buttons.addWidget(self.apply_btn)
        buttons.addWidget(self.reset_btn)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        root.addLayout(buttons)

        self._apply_theme_qss()
        schedule_title_bar_theme(self, is_light=self._theme == "light")

    def _apply_theme_qss(self) -> None:
        light = self._theme == "light"
        if light:
            bg, text, panel, border = "#f8fafc", "#0f172a", "#ffffff", "#cbd5e1"
            nav_hover, nav_sel = "rgba(30,64,175,0.10)", "rgba(29,78,216,0.16)"
            btn_bg, btn_text, btn_hover = "#e2e8f0", "#0f172a", "#cbd5e1"
        else:
            bg, text, panel, border = "#111827", "#e5e7eb", "#0f172a", "#334155"
            nav_hover, nav_sel = "rgba(56,189,248,0.14)", "rgba(56,189,248,0.22)"
            btn_bg, btn_text, btn_hover = "#1f2937", "#e5e7eb", "#273548"

        self.setStyleSheet(
            f"""
            QDialog {{
                font-family: "Segoe UI";
                font-size: 12px;
                background: {bg};
                color: {text};
            }}
            QLabel#CfgTitle {{ font-size: 19px; font-weight: 800; color: {text}; }}
            QListWidget#CfgNav {{
                border: 1px solid {border};
                border-radius: 10px;
                background: {panel};
                outline: none;
                padding: 6px;
            }}
            QListWidget#CfgNav::item {{
                padding: 9px 10px;
                border-radius: 8px;
                margin: 2px 0;
                color: {text};
            }}
            QListWidget#CfgNav::item:hover {{ background: {nav_hover}; }}
            QListWidget#CfgNav::item:selected {{ background: {nav_sel}; font-weight: 700; }}
            QWidget#CfgPanel {{
                border: 1px solid {border};
                border-radius: 10px;
                background: {panel};
            }}
            QLineEdit, QComboBox {{
                border: 1px solid {border};
                border-radius: 6px;
                padding: 5px 7px;
                background: {panel};
                color: {text};
            }}
            QPushButton {{
                border: 1px solid {border};
                border-radius: 7px;
                padding: 6px 10px;
                background: {btn_bg};
                color: {btn_text};
                font-weight: 700;
            }}
            QPushButton:hover {{ background: {btn_hover}; }}
            """
        )

    def _make_panel(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        panel = QWidget()
        panel.setObjectName("CfgPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setStyleSheet("font-weight: 800;")
        layout.addWidget(heading)
        return panel, layout

    def _build_apariencia(self, current_theme: str) -> QWidget:
        panel, layout = self._make_panel("Apariencia")
        form = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Sistema operativo", "Oscuro", "Claro"])
        if current_theme == "system":
            self.theme_combo.setCurrentText("Sistema operativo")
        else:
            self.theme_combo.setCurrentText("Claro" if current_theme == "light" else "Oscuro")
        self.theme_combo.currentTextChanged.connect(self._preview_theme)
        form.addRow("Tema", self.theme_combo)
        layout.addLayout(form)
        layout.addStretch(1)
        return panel

    def _path_row(self, form: QFormLayout, label: str, value: str) -> QLineEdit:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        edit = QLineEdit(value)
        btn = QPushButton("...")
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self._choose_path(edit))
        edit.textChanged.connect(lambda: self._validate_path_field(edit))
        row.addWidget(edit, 1)
        row.addWidget(btn)
        form.addRow(label, holder)
        self._validate_path_field(edit)
        return edit

    def _build_rutas(self, data_dir: str, log_dir: str, exports_dir: str, spool_dir: str) -> QWidget:
        panel, layout = self._make_panel("Rutas")
        form = QFormLayout()
        self.path_data = self._path_row(form, "Data", data_dir)
        self.path_logs = self._path_row(form, "Logs", log_dir)
        self.path_exports = self._path_row(form, "Exportaciones", exports_dir)
        self.path_spool = self._path_row(form, "Spool impresion", spool_dir)
        layout.addLayout(form)
        layout.addStretch(1)
        return panel

    def _choose_path(self, target: QLineEdit) -> None:
        current = target.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta", current)
        if selected:
            target.setText(selected)

    def _validate_path_field(self, edit: QLineEdit) -> None:
        value = edit.text().strip()
        if not value:
            edit.setStyleSheet("")
            return
        exists = Path(value).exists()
        edit.setStyleSheet(
            "border: 1px solid #22c55e; border-radius: 4px;" if exists else "border: 1px solid #ef4444; border-radius: 4px;"
        )

    def _preview_theme(self) -> None:
        self._theme_pref = self._theme_value_from_combo()
        self._theme = self._resolve_effective_theme(self._theme_pref)
        self._apply_theme_qss()
        schedule_title_bar_theme(self, is_light=self._theme == "light")

    def _on_reset_clicked(self) -> None:
        if QMessageBox.question(self, "Restaurar", "Se restauraran valores por defecto. Continuar?") != QMessageBox.Yes:
            return
        defaults = AppConfig()
        if defaults.theme == "system":
            self.theme_combo.setCurrentText("Sistema operativo")
        else:
            self.theme_combo.setCurrentText("Claro" if defaults.theme == "light" else "Oscuro")
        self.path_data.setText(defaults.data_dir)
        self.path_logs.setText(defaults.log_dir)
        self.path_exports.setText(defaults.exports_dir)
        self.path_spool.setText(defaults.print_spool_dir)

    def _on_export_clicked(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar configuracion", "config_reporte_docente.json", "JSON (*.json)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.values(), fh, ensure_ascii=False, indent=2)

    def _on_import_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar configuracion", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            QMessageBox.warning(self, "Config", f"No se pudo importar: {exc}")
            return
        self._loaded_config = data
        imported_theme = str(data.get("theme", "")).strip().lower()
        if imported_theme in {"system", "sistema", "auto"}:
            self.theme_combo.setCurrentText("Sistema operativo")
        if imported_theme in {"light", "white", "claro"}:
            self.theme_combo.setCurrentText("Claro")
        elif imported_theme in {"dark", "oscuro"}:
            self.theme_combo.setCurrentText("Oscuro")
        self.path_data.setText(str(data.get("data_dir", self.path_data.text())))
        self.path_logs.setText(str(data.get("log_dir", self.path_logs.text())))
        self.path_exports.setText(str(data.get("exports_dir", self.path_exports.text())))
        self.path_spool.setText(str(data.get("print_spool_dir", self.path_spool.text())))

    def _on_apply_clicked(self) -> None:
        if callable(self._apply_callback):
            self._apply_callback(self.to_config())

    def values(self) -> dict[str, object]:
        out = {
            "theme": self._theme_value_from_combo(),
            "data_dir": self.path_data.text().strip(),
            "log_dir": self.path_logs.text().strip(),
            "exports_dir": self.path_exports.text().strip(),
            "print_spool_dir": self.path_spool.text().strip(),
        }
        if isinstance(self._loaded_config, dict):
            loaded = dict(self._loaded_config)
            loaded.update(out)
            return loaded
        return out

    def to_config(self) -> AppConfig:
        values = self.values()
        return AppConfig(
            theme=str(values.get("theme", "dark")),
            data_dir=str(values.get("data_dir", "")),
            log_dir=str(values.get("log_dir", "")),
            exports_dir=str(values.get("exports_dir", "")),
            print_spool_dir=str(values.get("print_spool_dir", "")),
        )

    def _theme_value_from_combo(self) -> str:
        text = self.theme_combo.currentText()
        if text == "Claro":
            return "light"
        if text == "Oscuro":
            return "dark"
        return "system"

    def _resolve_effective_theme(self, pref: str) -> str:
        if pref in {"light", "dark"}:
            return pref
        return "dark" if is_system_dark() else "light"
