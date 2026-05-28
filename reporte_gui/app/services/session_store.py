from __future__ import annotations

import json
from pathlib import Path


def _store_path(data_dir: Path) -> Path:
    return data_dir / "_session_store.json"


def load_session(data_dir: Path) -> dict[str, str]:
    path = _store_path(data_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        return {}
    return {}


def save_session(data_dir: Path, values: dict[str, str]) -> None:
    path = _store_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")

