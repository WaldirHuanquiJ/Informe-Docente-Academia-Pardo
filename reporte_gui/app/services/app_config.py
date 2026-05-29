from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DOCUMENTS_DIR = Path.home() / "Documents"
DEFAULT_OUTPUT_DIR = (DOCUMENTS_DIR / "Reporte Docente").expanduser()
DEFAULT_DATA_DIR = DEFAULT_OUTPUT_DIR / "data"
DEFAULT_LOG_DIR = DEFAULT_OUTPUT_DIR / "logs"
DEFAULT_EXPORTS_DIR = DEFAULT_OUTPUT_DIR / "exports"
DEFAULT_PRINT_SPOOL_DIR = DEFAULT_OUTPUT_DIR / "print_spool"
CONFIG_PATH = DEFAULT_DATA_DIR / "_app_config.json"
LEGACY_DATA_DIR = BASE_DIR / "data"


@dataclass
class AppConfig:
    theme: str = "system"
    data_dir: str = str(DEFAULT_DATA_DIR)
    log_dir: str = str(DEFAULT_LOG_DIR)
    exports_dir: str = str(DEFAULT_EXPORTS_DIR)
    print_spool_dir: str = str(DEFAULT_PRINT_SPOOL_DIR)


def _normalize_theme(theme: str) -> str:
    value = (theme or "").strip().lower()
    if value in {"system", "sistema", "auto"}:
        return "system"
    return "light" if value in {"light", "white", "claro"} else "dark"


def _coerce_dir(raw: str, fallback: Path) -> str:
    path = Path(raw).expanduser() if raw else fallback
    if not path.is_absolute():
        path = DEFAULT_OUTPUT_DIR / path
    # En ejecutable empaquetado se fuerza almacenamiento en area de usuario.
    if getattr(sys, "frozen", False):
        try:
            exe_dir = Path(sys.executable).resolve().parent
            path.resolve().relative_to(exe_dir)
            path = fallback
        except Exception:
            pass
    return str(path)


def ensure_dirs(config: AppConfig) -> None:
    data_dir = Path(config.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "horario").mkdir(parents=True, exist_ok=True)
    (data_dir / "biometrico").mkdir(parents=True, exist_ok=True)
    Path(config.log_dir).mkdir(parents=True, exist_ok=True)
    Path(config.exports_dir).mkdir(parents=True, exist_ok=True)
    Path(config.print_spool_dir).mkdir(parents=True, exist_ok=True)


def bootstrap_legacy_data(config: AppConfig) -> None:
    data_dir = Path(config.data_dir)
    if not LEGACY_DATA_DIR.exists() or LEGACY_DATA_DIR.resolve() == data_dir.resolve():
        return
    route_map = {
        "HORARIOS.xlsx": data_dir / "horario" / "HORARIOS.xlsx",
        "Libro1.csv": data_dir / "biometrico" / "Libro1.csv",
        "_runtime_report.csv": data_dir / "biometrico" / "_runtime_report.csv",
    }
    for name, dst in route_map.items():
        src = LEGACY_DATA_DIR / name
        if src.exists() and not dst.exists():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            except Exception:
                pass
    # Copiar tambien versiones de horario (HORARIOS_YYYYMMDD.xlsx), que son la base actual.
    for src in list(LEGACY_DATA_DIR.glob("HORARIOS*.xlsx")) + list((LEGACY_DATA_DIR / "horario").glob("HORARIOS*.xlsx")):
        dst = data_dir / "horario" / src.name
        if not dst.exists():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            except Exception:
                pass
    for xls in list(LEGACY_DATA_DIR.glob("*.xls")) + list((LEGACY_DATA_DIR / "biometrico").glob("*.xls")):
        dst = data_dir / "biometrico" / xls.name
        if not dst.exists():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(xls, dst)
            except Exception:
                pass
    for csv in list(LEGACY_DATA_DIR.glob("*.csv")) + list((LEGACY_DATA_DIR / "biometrico").glob("*.csv")):
        dst = data_dir / "biometrico" / csv.name
        if not dst.exists():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(csv, dst)
            except Exception:
                pass


def normalize_config(config: AppConfig) -> AppConfig:
    return AppConfig(
        theme=_normalize_theme(config.theme),
        data_dir=_coerce_dir(config.data_dir, DEFAULT_DATA_DIR),
        log_dir=_coerce_dir(config.log_dir, DEFAULT_LOG_DIR),
        exports_dir=_coerce_dir(
            config.exports_dir or os.environ.get("REPORTE_DOCENTE_EXPORTS_DIR", ""),
            DEFAULT_EXPORTS_DIR,
        ),
        print_spool_dir=_coerce_dir(
            config.print_spool_dir or os.environ.get("REPORTE_DOCENTE_PRINT_SPOOL_DIR", ""),
            DEFAULT_PRINT_SPOOL_DIR,
        ),
    )


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        cfg = normalize_config(AppConfig())
        ensure_dirs(cfg)
        save_config(cfg)
        return cfg
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cfg = AppConfig(
            theme=str(payload.get("theme", "dark")),
            data_dir=str(payload.get("data_dir", DEFAULT_DATA_DIR)),
            log_dir=str(payload.get("log_dir", DEFAULT_LOG_DIR)),
            exports_dir=str(payload.get("exports_dir", DEFAULT_EXPORTS_DIR)),
            print_spool_dir=str(payload.get("print_spool_dir", DEFAULT_PRINT_SPOOL_DIR)),
        )
    except Exception:
        cfg = AppConfig()
    cfg = normalize_config(cfg)
    ensure_dirs(cfg)
    bootstrap_legacy_data(cfg)
    return cfg


def save_config(config: AppConfig) -> None:
    cfg = normalize_config(config)
    ensure_dirs(cfg)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
