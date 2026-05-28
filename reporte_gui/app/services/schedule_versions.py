from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

_VERSIONED_NAME_RE = re.compile(r"^HORARIOS?_(\d{8})\.(xlsx|xls)$", re.IGNORECASE)


def parse_versioned_schedule_date(path: Path) -> date | None:
    match = _VERSIONED_NAME_RE.match(path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def list_versioned_schedules(schedule_dir: Path) -> list[tuple[date, Path]]:
    found: list[tuple[date, Path]] = []
    if not schedule_dir.exists():
        return found
    for pattern in ("HORARIO_*.xlsx", "HORARIOS_*.xlsx", "HORARIO_*.xls", "HORARIOS_*.xls"):
        for path in schedule_dir.glob(pattern):
            parsed = parse_versioned_schedule_date(path)
            if parsed is None:
                continue
            found.append((parsed, path))
    # Evita duplicados por coincidencias múltiples de patrón.
    uniq: dict[tuple[date, str], Path] = {}
    for dt, p in found:
        uniq[(dt, str(p.resolve()).lower())] = p
    found = [(k[0], v) for k, v in uniq.items()]
    found.sort(key=lambda item: item[0])
    return found


def resolve_schedule_for_date(
    schedule_dir: Path,
    target_date: date,
    fallback_path: Path | None = None,
) -> Path | None:
    versions = list_versioned_schedules(schedule_dir)
    chosen: Path | None = None
    for start_date, path in versions:
        if start_date <= target_date:
            chosen = path
        else:
            break
    if chosen is not None:
        return chosen
    if fallback_path and fallback_path.exists():
        return fallback_path
    return None
