from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtCore import Qt
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget, QWidget, QHBoxLayout, QToolButton, QStyle

from app.services.biometric_import import export_report_sheet_to_csv, resolve_report_csv
from app.services.report_parser import parse_report
from app.services.session_store import load_session, save_session
from app.models import TeacherRecord
from app.ui.dashboard import DashboardView
from app.ui.horario import HorarioView
from app.ui.calendario import CalendarioView
from app.ui.informe import InformeView
from app.ui.reporte import ReporteView
from app.ui.resumen import ResumenView
from app.ui.styles import DARK_THEME, LIGHT_THEME
from app.ui.icon_factory import make_gear_icon, make_help_icon, make_info_icon, set_icon_theme
from app.ui.settings_dialog import SettingsDialog
from app.ui.help_dialog import HelpDialog
from app.ui.info_dialog import InfoDialog
from app.ui.window_theme import schedule_title_bar_theme
from app.services.app_config import AppConfig, save_config
from app.services.system_theme import is_system_dark


class ImportWorker(QObject):
    finished = Signal(object, object)  # (Path|None, report|None)
    failed = Signal(str)

    def __init__(self, data_dir: Path, current_report_path: Path, selected_file: Path | None = None) -> None:
        super().__init__()
        self._data_dir = data_dir
        self._current_report_path = current_report_path
        self._selected_file = selected_file

    def run(self) -> None:
        try:
            if self._selected_file and self._selected_file.exists():
                suffix = self._selected_file.suffix.lower()
                if suffix == ".csv":
                    updated = self._selected_file
                else:
                    out_csv = self._data_dir / "_runtime_report.csv"
                    ok = export_report_sheet_to_csv(self._selected_file, out_csv, "Reporte de Asistencia")
                    if not ok:
                        raise RuntimeError("No se pudo convertir la hoja 'Reporte de Asistencia' del XLS seleccionado.")
                    updated = out_csv
            else:
                updated = resolve_report_csv(self._data_dir)
            report_path = updated if updated and updated.exists() else self._current_report_path
            report = parse_report(report_path)
            self.finished.emit(report_path, report)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path, config: AppConfig) -> None:
        super().__init__()
        self.setWindowTitle("Reporte Docente")
        self.resize(1280, 780)
        self.setMinimumSize(1080, 680)
        schedule_title_bar_theme(self, is_light=self._effective_theme(config.theme) == "light")

        self.data_dir = data_dir
        self._config = config
        self.report_path: Path | None = None
        self.report = None
        self._import_thread: QThread | None = None
        self._import_worker: ImportWorker | None = None
        self._horario_thread: QThread | None = None
        self._horario_worker: QObject | None = None
        self._syncing_teacher_selection = False
        self._dashboard_needs_refresh = False
        self._informe_needs_refresh = False
        self._resumen_needs_refresh = False
        self._dashboard_panel_dirty = False
        self._informe_panel_dirty = False
        self._selected_teacher_key: tuple[str, str, str] | None = None

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self._setup_tab_actions()

        self.horario_view = HorarioView(self.data_dir)
        self.calendario_view = CalendarioView(self.data_dir)
        self.reporte_view = ReporteView(self.data_dir)
        self.dashboard = DashboardView(self.data_dir)
        self.informe_view = InformeView(self.data_dir)
        self.resumen_view = ResumenView(self.data_dir)
        self._refresh_theme_icons()
        self.reporte_view.set_theme_mode(self._effective_theme(self._config.theme))
        self.informe_view.set_theme_mode(self._effective_theme(self._config.theme))
        self.resumen_view.set_theme_mode(self._effective_theme(self._config.theme))
        self.informe_view.set_runtime_dirs(
            exports_dir=Path(self._config.exports_dir),
            print_spool_dir=Path(self._config.print_spool_dir),
        )

        self.tabs.addTab(self.horario_view.tab, "Horario")
        self.tabs.addTab(self.calendario_view.tab, "Calendario")
        self.tabs.addTab(self.reporte_view.tab, "Reporte de Asistencia")
        self.tabs.addTab(self.dashboard.tab, "Dashboard")
        self.tabs.addTab(self.informe_view.tab, "Informe")
        self.tabs.addTab(self.resumen_view.tab, "Resumen")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.horario_view.on_import_horario = self.import_horario_file
        self.horario_view.on_clear = self.clear_horario_tab
        self.calendario_view.on_calendar_updated = self._on_calendar_updated
        self.reporte_view.on_import_xls = self.reload_report_async
        self.reporte_view.on_clear = self.clear_reporte_tab
        self.dashboard.teacher_selector.currentIndexChanged.connect(self._sync_from_dashboard_to_informe)
        self.informe_view.teacher_selector.currentIndexChanged.connect(self._sync_from_informe_to_dashboard)
        self._restore_or_start_empty()

    def _setup_tab_actions(self) -> None:
        corner = QWidget(self.tabs)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(4)

        self.btn_settings = QToolButton(corner)
        self.btn_help = QToolButton(corner)
        self.btn_info = QToolButton(corner)

        self.btn_settings.setIcon(make_gear_icon(20))
        self.btn_help.setIcon(make_help_icon(20))
        self.btn_info.setIcon(make_info_icon(20))
        self.btn_settings.setIconSize(QSize(20, 20))
        self.btn_help.setIconSize(QSize(20, 20))
        self.btn_info.setIconSize(QSize(20, 20))

        for btn, tip in (
            (self.btn_settings, "Configuracion"),
            (self.btn_help, "Ayuda"),
            (self.btn_info, "Informacion"),
        ):
            btn.setToolTip(tip)
            btn.setAutoRaise(True)
            btn.setCursor(Qt.PointingHandCursor)
            layout.addWidget(btn)
        self._apply_corner_button_theme()

        self.btn_settings.clicked.connect(self._show_settings_info)
        self.btn_help.clicked.connect(self._show_help_info)
        self.btn_info.clicked.connect(self._show_about_info)

        corner.setLayout(layout)
        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)

    def _show_settings_info(self) -> None:
        dialog = SettingsDialog(self._config, self)
        if dialog.exec():
            new_cfg = dialog.to_config()
            save_config(new_cfg)
            self._config = new_cfg
            self.data_dir = Path(new_cfg.data_dir)
            self.informe_view.set_runtime_dirs(
                exports_dir=Path(new_cfg.exports_dir),
                print_spool_dir=Path(new_cfg.print_spool_dir),
            )
            app = QApplication.instance()
            effective_theme = self._effective_theme(new_cfg.theme)
            self.reporte_view.set_theme_mode(effective_theme)
            self.informe_view.set_theme_mode(effective_theme)
            self.resumen_view.set_theme_mode(effective_theme)
            if app is not None:
                app.setStyleSheet(LIGHT_THEME if effective_theme == "light" else DARK_THEME)
            schedule_title_bar_theme(self, is_light=effective_theme == "light")
            self._refresh_theme_icons()
            self._apply_corner_button_theme()
            QMessageBox.information(self, "Configuracion", "Cambios aplicados correctamente.")

    def _apply_corner_button_theme(self) -> None:
        hover_bg = "rgba(0,0,0,0.07)" if self._effective_theme(self._config.theme) == "light" else "rgba(255,255,255,0.06)"
        style = (
            "QToolButton { background: transparent; border: none; padding: 4px; }"
            f"QToolButton:hover {{ background: {hover_bg}; border-radius: 10px; }}"
        )
        self.btn_settings.setStyleSheet(style)
        self.btn_help.setStyleSheet(style)
        self.btn_info.setStyleSheet(style)

    def _refresh_theme_icons(self) -> None:
        set_icon_theme(self._effective_theme(self._config.theme))
        self.btn_settings.setIcon(make_gear_icon(20))
        self.btn_help.setIcon(make_help_icon(20))
        self.btn_info.setIcon(make_info_icon(20))
        if hasattr(self, "horario_view"):
            self.horario_view.refresh_icons()
        if hasattr(self, "reporte_view"):
            self.reporte_view.refresh_icons()
        if hasattr(self, "informe_view"):
            self.informe_view.refresh_icons()
        if hasattr(self, "calendario_view"):
            self.calendario_view.refresh_icons()

    def _effective_theme(self, pref: str) -> str:
        if pref in {"light", "dark"}:
            return pref
        return "dark" if is_system_dark() else "light"

    def _show_help_info(self) -> None:
        dialog = HelpDialog(self, theme_mode=self._effective_theme(self._config.theme))
        dialog.exec()

    def _show_about_info(self) -> None:
        dialog = InfoDialog(self, theme_mode=self._effective_theme(self._config.theme))
        dialog.exec()

    def refresh_data(self) -> None:
        if not self.report:
            return
        self.horario_view.set_teachers(self.report.teachers)
        self.reporte_view.set_report(self.report)
        # Precarga completa para que el cambio de pestañas sea inmediato.
        self.dashboard.refresh(self.report)
        self.informe_view.set_report(self.report)
        self.resumen_view.refresh(self.report)
        self._dashboard_needs_refresh = False
        self._informe_needs_refresh = False
        self._resumen_needs_refresh = False
        self._dashboard_panel_dirty = False
        self._informe_panel_dirty = False
        self._sync_from_dashboard_to_informe()

    def _refresh_visible_heavy_tabs(self) -> None:
        if not self.report:
            return
        idx = self.tabs.currentIndex()
        # Dashboard tab
        if self._dashboard_needs_refresh and idx == 3:
            self.dashboard.refresh(self.report)
            self._restore_selected_teacher(self.dashboard.teacher_selector)
            self.dashboard._refresh_teacher_panel()
            self._dashboard_needs_refresh = False
            self._dashboard_panel_dirty = False
        # Informe tab
        if self._informe_needs_refresh and idx == 4:
            self.informe_view.set_report(self.report)
            self._restore_selected_teacher(self.informe_view.teacher_selector)
            self.informe_view._refresh_all()
            self._informe_needs_refresh = False
            self._informe_panel_dirty = False
        if self._resumen_needs_refresh and idx == 5:
            self.resumen_view.refresh(self.report)
            self._resumen_needs_refresh = False
        # Si ambos están listos, mantener sincronía de selector.
        if idx == 3 and self._dashboard_panel_dirty:
            self.dashboard._refresh_teacher_panel()
            self._dashboard_panel_dirty = False
        if idx == 4 and self._informe_panel_dirty:
            self.informe_view._refresh_all()
            self._informe_panel_dirty = False

    def _on_tab_changed(self, _index: int) -> None:
        self._refresh_visible_heavy_tabs()
        if _index == 5 and self.report:
            self.resumen_view.refresh(self.report)
            self._resumen_needs_refresh = False

    def _on_calendar_updated(self) -> None:
        if not self.report:
            return
        self.reporte_view.refresh_table()
        current_idx = self.tabs.currentIndex()
        if current_idx == 3:
            self.dashboard.refresh(self.report)
            self._restore_selected_teacher(self.dashboard.teacher_selector)
            self.dashboard._refresh_teacher_panel()
            self._dashboard_needs_refresh = False
            self._dashboard_panel_dirty = False
        else:
            self._dashboard_needs_refresh = True
            self._dashboard_panel_dirty = True
        if current_idx == 4:
            self.informe_view.set_report(self.report)
            self._restore_selected_teacher(self.informe_view.teacher_selector)
            self.informe_view._refresh_all()
            self._informe_needs_refresh = False
            self._informe_panel_dirty = False
        else:
            self._informe_needs_refresh = True
            self._informe_panel_dirty = True
        if current_idx == 5:
            self.resumen_view.refresh(self.report)
            self._resumen_needs_refresh = False
        else:
            self._resumen_needs_refresh = True

    def _teacher_key(self, teacher: TeacherRecord) -> tuple[str, str, str]:
        return (
            (teacher.teacher_id or "").strip(),
            (teacher.name or "").strip(),
            (teacher.department or "").strip(),
        )

    def _restore_selected_teacher(self, target_combo) -> bool:
        if self._selected_teacher_key is None or target_combo.count() == 0:
            return False
        target_combo.blockSignals(True)
        try:
            for idx in range(target_combo.count()):
                data = target_combo.itemData(idx)
                if isinstance(data, TeacherRecord) and self._teacher_key(data) == self._selected_teacher_key:
                    target_combo.setCurrentIndex(idx)
                    return True
        finally:
            target_combo.blockSignals(False)
        return False

    def _sync_selector_to_teacher(self, target_combo, teacher: TeacherRecord) -> bool:
        if target_combo.count() == 0:
            return False
        wanted = self._teacher_key(teacher)
        for idx in range(target_combo.count()):
            data = target_combo.itemData(idx)
            if not isinstance(data, TeacherRecord):
                continue
            if self._teacher_key(data) == wanted:
                target_combo.setCurrentIndex(idx)
                return True
        return False

    def _sync_from_dashboard_to_informe(self) -> None:
        if self._syncing_teacher_selection:
            return
        teacher = self.dashboard.teacher_selector.currentData()
        if not isinstance(teacher, TeacherRecord):
            return
        self._selected_teacher_key = self._teacher_key(teacher)
        self._syncing_teacher_selection = True
        synced = False
        changed = False
        try:
            self.informe_view.teacher_selector.blockSignals(True)
            before = self.informe_view.teacher_selector.currentIndex()
            synced = self._sync_selector_to_teacher(self.informe_view.teacher_selector, teacher)
            changed = synced and self.informe_view.teacher_selector.currentIndex() != before
        finally:
            self.informe_view.teacher_selector.blockSignals(False)
            self._syncing_teacher_selection = False
        if self.tabs.currentIndex() == 4 and synced:
            self.informe_view._refresh_all()
            self._informe_panel_dirty = False
        else:
            self._informe_panel_dirty = synced or changed or self._informe_panel_dirty

    def _sync_from_informe_to_dashboard(self) -> None:
        if self._syncing_teacher_selection:
            return
        teacher = self.informe_view.teacher_selector.currentData()
        if not isinstance(teacher, TeacherRecord):
            return
        self._selected_teacher_key = self._teacher_key(teacher)
        self._syncing_teacher_selection = True
        synced = False
        changed = False
        try:
            self.dashboard.teacher_selector.blockSignals(True)
            before = self.dashboard.teacher_selector.currentIndex()
            synced = self._sync_selector_to_teacher(self.dashboard.teacher_selector, teacher)
            changed = synced and self.dashboard.teacher_selector.currentIndex() != before
        finally:
            self.dashboard.teacher_selector.blockSignals(False)
            self._syncing_teacher_selection = False
        if self.tabs.currentIndex() == 3 and synced:
            self.dashboard._refresh_teacher_panel()
            self._dashboard_panel_dirty = False
        else:
            self._dashboard_panel_dirty = synced or changed or self._dashboard_panel_dirty

    def reload_report(self) -> None:
        try:
            updated = resolve_report_csv(self.data_dir)
            if updated and updated.exists():
                self.report_path = updated
            if not self.report_path:
                raise RuntimeError("No hay fuente de reporte seleccionada.")
            self.report = parse_report(self.report_path)
            self.horario_view.reload()
            self.refresh_data()
            self._save_session_paths()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"No se pudo recargar el reporte:\n{exc}")

    def reload_report_async(self, selected_file: Path | None = None) -> None:
        if self._import_thread and self._import_thread.isRunning():
            return

        self.reporte_view.import_xls_button.setEnabled(False)
        self.reporte_view.import_xls_button.setText("Importando...")
        self.reporte_view.table.setRowCount(0)
        self.reporte_view.table.setColumnCount(0)
        self.reporte_view.info_label.setText("Importando biometrico (XLS/CSV)... espere un momento.")

        self._import_thread = QThread(self)
        self._import_worker = ImportWorker(self.data_dir, self.report_path or (self.data_dir / "_runtime_report.csv"), selected_file)
        self._import_worker.moveToThread(self._import_thread)

        self._import_thread.started.connect(self._import_worker.run)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.failed.connect(self._on_import_failed)
        self._import_worker.finished.connect(self._import_thread.quit)
        self._import_worker.failed.connect(self._import_thread.quit)
        self._import_thread.finished.connect(self._on_import_cleanup)
        self._import_thread.start()

    def _on_import_finished(self, report_path: Path, report) -> None:
        self.report_path = report_path
        self.report = report
        self.horario_view.reload()
        self.refresh_data()
        self._save_session_paths()

    def _on_import_failed(self, error: str) -> None:
        QMessageBox.critical(self, "Error", f"No se pudo importar el archivo biometrico:\n{error}")

    def _on_import_cleanup(self) -> None:
        self.reporte_view.import_xls_button.setEnabled(True)
        self.reporte_view.import_xls_button.setText("Importar XLS/CSV biometrico")
        if self._import_worker:
            self._import_worker.deleteLater()
            self._import_worker = None
        if self._import_thread:
            self._import_thread.deleteLater()
            self._import_thread = None

    def import_horario_file(self, selected_path: Path | list[Path]) -> None:
        try:
            selected_list = selected_path if isinstance(selected_path, list) else [selected_path]
            if not selected_list:
                raise FileNotFoundError("No se seleccionaron archivos de horario.")
            for p in selected_list:
                if not p.exists():
                    raise FileNotFoundError(f"Archivo de horario no encontrado: {p}")
            self.horario_view.import_horario_button.setEnabled(False)
            self.horario_view.import_horario_button.setText("Importando horario...")
            self.horario_view.table.setRowCount(0)
            self.horario_view.table.setColumnCount(0)

            imported_targets: list[Path] = []
            for p in selected_list:
                if p.resolve().parent == self.data_dir.resolve():
                    imported_targets.append(p)
                    continue
                target = self.data_dir / p.name
                shutil.copy2(p, target)
                imported_targets.append(target)

            active_path = sorted(imported_targets, key=lambda x: x.name)[-1]
            self.horario_view.set_schedule_file(active_path)
            self.calendario_view.set_schedule_file(active_path)
            self.reporte_view.set_schedule_file(active_path)
            self.dashboard.set_schedule_file(active_path)
            self.informe_view.set_schedule_file(active_path)
            self.resumen_view.set_schedule_file(active_path)
            self._on_horario_import_finished()
            self._save_session_paths()
        except Exception as exc:  # noqa: BLE001
            self._on_horario_import_failed(str(exc))
        finally:
            self._on_horario_import_cleanup()

    def _on_horario_import_finished(self) -> None:
        self.horario_view.reload()
        self.reporte_view.reload_schedule_source()
        self.dashboard.reload_schedule_source()
        self.informe_view.reload_schedule_source()
        self.resumen_view.reload_schedule_source()
        self.refresh_data()

    def _on_horario_import_failed(self, error: str) -> None:
        QMessageBox.critical(self, "Error", f"No se pudo importar el horario:\n{error}")

    def _on_horario_import_cleanup(self) -> None:
        self.horario_view.import_horario_button.setEnabled(True)
        self.horario_view.import_horario_button.setText("Importar Horario")
        if self._horario_worker:
            self._horario_worker.deleteLater()
            self._horario_worker = None
        if self._horario_thread:
            self._horario_thread.deleteLater()
            self._horario_thread = None

    def _restore_or_start_empty(self) -> None:
        session = load_session(self.data_dir)
        schedule_path = self._resolve_saved_or_local_schedule(session.get("schedule_path"))
        report_path = self._resolve_saved_or_local_report(session.get("report_path"))

        # Si hay horario guardado y existe, se restaura.
        if schedule_path and schedule_path.exists():
            self.horario_view.set_schedule_file(schedule_path)
            self.calendario_view.set_schedule_file(schedule_path)
            self.reporte_view.set_schedule_file(schedule_path)
            self.dashboard.set_schedule_file(schedule_path)
            self.informe_view.set_schedule_file(schedule_path)
            self.resumen_view.set_schedule_file(schedule_path)
            self.horario_view.reload()
        else:
            self.horario_view.clear_all()

        # Si hay reporte guardado y existe, se restaura todo automaticamente.
        if report_path and report_path.exists():
            try:
                self.report_path = report_path
                self.report = parse_report(report_path)
                self.refresh_data()
                self._save_session_paths()
            except Exception:
                # Memoria invalida: limpiar y continuar en blanco.
                self.report_path = None
                self.report = None
                self.reporte_view.clear_all()
                self.dashboard.clear_all()
                self.informe_view.clear_all()
                self.resumen_view.clear_all()
                session.pop("report_path", None)
                save_session(self.data_dir, session)
        else:
            self.reporte_view.clear_all()
            self.dashboard.clear_all()
            self.informe_view.clear_all()
            self.resumen_view.clear_all()

    def _resolve_saved_or_local_schedule(self, saved_path: str | None) -> Path | None:
        if saved_path:
            path = Path(saved_path)
            if path.exists():
                return path
        direct = self.data_dir / "HORARIOS.xlsx"
        if direct.exists():
            return direct
        candidates = sorted(
            self.data_dir.glob("HORARIOS*.xlsx"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
        return candidates[0] if candidates else None

    def _resolve_saved_or_local_report(self, saved_path: str | None) -> Path | None:
        if saved_path:
            path = Path(saved_path)
            if path.exists():
                return path
        for name in ("_runtime_report.csv", "Libro1.csv"):
            candidate = self.data_dir / name
            if candidate.exists():
                return candidate
        return resolve_report_csv(self.data_dir)

    def _save_session_paths(self) -> None:
        payload: dict[str, str] = {}
        if self.report_path and self.report_path.exists():
            payload["report_path"] = str(self.report_path)
        if hasattr(self.horario_view, "_schedule_path"):
            sp = getattr(self.horario_view, "_schedule_path")
            if isinstance(sp, Path) and sp.exists():
                payload["schedule_path"] = str(sp)
        save_session(self.data_dir, payload)

    def clear_all_data(self) -> None:
        self.report = None
        self.report_path = None

        self.horario_view.clear_all()
        self.reporte_view.clear_all()
        self.dashboard.clear_all()
        self.informe_view.clear_all()
        self.resumen_view.clear_all()

        # Resetea almacenamiento de sesion
        save_session(self.data_dir, {})

    def clear_horario_tab(self) -> None:
        self.horario_view.clear_all()
        session = load_session(self.data_dir)
        session.pop("schedule_path", None)
        save_session(self.data_dir, session)

    def clear_reporte_tab(self) -> None:
        self.report = None
        self.report_path = None
        self.reporte_view.clear_all()
        self.dashboard.clear_all()
        self.informe_view.clear_all()
        self.resumen_view.clear_all()
        session = load_session(self.data_dir)
        session.pop("report_path", None)
        save_session(self.data_dir, session)
