from __future__ import annotations

import json
from pathlib import Path


def _calendar_path(data_dir: Path) -> Path:
    return data_dir / "labor_calendar.json"


def load_calendar(data_dir: Path) -> dict:
    path = _calendar_path(data_dir)
    if not path.exists():
        return {"months": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("months"), dict):
            return data
    except Exception:
        pass
    return {"months": {}}


def save_calendar(data_dir: Path, payload: dict) -> None:
    path = _calendar_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"

