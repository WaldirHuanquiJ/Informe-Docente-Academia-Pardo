from __future__ import annotations

import json
from pathlib import Path

from app.services.app_config import DEFAULT_DATA_DIR, load_config


def _store_path() -> Path:
    try:
        cfg = load_config()
        return Path(cfg.data_dir) / "weekly_hours_store.json"
    except Exception:
        return DEFAULT_DATA_DIR / "weekly_hours_store.json"


def _read_store() -> dict[str, float]:
    store_path = _store_path()
    if not store_path.exists():
        return {}
    try:
        data = json.loads(store_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): float(v) for k, v in data.items()}
    except Exception:
        return {}
    return {}


def _write_store(payload: dict[str, float]) -> None:
    store_path = _store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_weekly_hours(teacher_id: str, week_key: str) -> float:
    data = _read_store()
    return float(data.get(f"{teacher_id}::{week_key}", 0.0))


def set_weekly_hours(teacher_id: str, week_key: str, hours: float) -> None:
    data = _read_store()
    data[f"{teacher_id}::{week_key}"] = float(hours)
    _write_store(data)
