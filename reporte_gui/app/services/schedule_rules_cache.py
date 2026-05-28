from __future__ import annotations

from pathlib import Path
from threading import RLock

from app.services.horario_excel import load_horarios_workbook
from app.services.schedule_utils import (
    extract_course_alias_pairs,
    extract_schedule_blocks,
    extract_schedule_blocks_with_continuity,
    norm_name,
    slot_indexes_for_label,
)

_LOCK = RLock()
_CACHE_BASIC: dict[tuple[str, int, int, str], tuple[dict[str, set[str]], dict[str, dict[int, set[int]]]]] = {}
_CACHE_MODALITY: dict[
    tuple[str, int, int],
    tuple[
        dict[str, set[str]],
        dict[str, dict[int, set[int]]],
        dict[str, dict[str, dict[int, set[int]]]],
    ],
] = {}


def _file_key(path: Path) -> tuple[str, int, int] | None:
    try:
        p = path.resolve()
        st = p.stat()
        return (str(p), int(st.st_mtime_ns), int(st.st_size))
    except Exception:
        return None


def get_basic_rules(
    xlsx_path: Path, *, continuity: bool
) -> tuple[dict[str, set[str]], dict[str, dict[int, set[int]]]]:
    key_base = _file_key(xlsx_path)
    cache_key = None if key_base is None else (key_base[0], key_base[1], key_base[2], "cont" if continuity else "block")
    if cache_key is not None:
        with _LOCK:
            cached = _CACHE_BASIC.get(cache_key)
            if cached is not None:
                return cached

    aliases_by_dept: dict[str, set[str]] = {}
    teacher_slots: dict[str, dict[int, set[int]]] = {}
    workbook = load_horarios_workbook(xlsx_path)
    for sheet in workbook.sheets:
        blocks = (
            extract_schedule_blocks_with_continuity(sheet.rows)
            if continuity
            else extract_schedule_blocks(sheet.rows)
        )
        for _headers, schedule_rows in blocks:
            for row in schedule_rows:
                for day_col in range(1, min(8, len(row))):
                    cell = (row[day_col] or "").strip()
                    if not cell:
                        continue
                    for course, alias in extract_course_alias_pairs(cell):
                        if not course or not alias:
                            continue
                        dept_key = norm_name(course)
                        alias_key = norm_name(alias)
                        aliases_by_dept.setdefault(dept_key, set()).add(alias_key)
                        slot_indexes = slot_indexes_for_label(row[0] if row else "")
                        if not slot_indexes:
                            continue
                        tkey = f"{alias_key}||{dept_key}"
                        by_day = teacher_slots.setdefault(tkey, {})
                        day_slots = by_day.setdefault(day_col - 1, set())
                        day_slots.update(slot_indexes)

    result = (aliases_by_dept, teacher_slots)
    if cache_key is not None:
        with _LOCK:
            if len(_CACHE_BASIC) > 64:
                _CACHE_BASIC.clear()
            _CACHE_BASIC[cache_key] = result
    return result


def get_rules_with_modality(
    xlsx_path: Path,
) -> tuple[
    dict[str, set[str]],
    dict[str, dict[int, set[int]]],
    dict[str, dict[str, dict[int, set[int]]]],
]:
    key = _file_key(xlsx_path)
    if key is not None:
        with _LOCK:
            cached = _CACHE_MODALITY.get(key)
            if cached is not None:
                return cached

    aliases_by_dept: dict[str, set[str]] = {}
    teacher_slots: dict[str, dict[int, set[int]]] = {}
    teacher_modality_slots: dict[str, dict[str, dict[int, set[int]]]] = {}
    workbook = load_horarios_workbook(xlsx_path)
    for sheet in workbook.sheets:
        blocks = extract_schedule_blocks(sheet.rows)
        for block_idx, (_headers, schedule_rows) in enumerate(blocks):
            modality_name = sheet.name if len(blocks) == 1 else f"{sheet.name} - T{block_idx + 1}"
            for row in schedule_rows:
                for day_col in range(1, min(8, len(row))):
                    cell = (row[day_col] or "").strip()
                    if not cell:
                        continue
                    for course, alias in extract_course_alias_pairs(cell):
                        if not course or not alias:
                            continue
                        dept_key = norm_name(course)
                        alias_key = norm_name(alias)
                        aliases_by_dept.setdefault(dept_key, set()).add(alias_key)
                        slot_indexes = slot_indexes_for_label(row[0] if row else "")
                        if not slot_indexes:
                            continue
                        tkey = f"{alias_key}||{dept_key}"
                        by_day = teacher_slots.setdefault(tkey, {})
                        day_slots = by_day.setdefault(day_col - 1, set())
                        day_slots.update(slot_indexes)
                        by_modality = teacher_modality_slots.setdefault(tkey, {})
                        by_weekday = by_modality.setdefault(modality_name, {})
                        mod_day_slots = by_weekday.setdefault(day_col - 1, set())
                        mod_day_slots.update(slot_indexes)

    result = (aliases_by_dept, teacher_slots, teacher_modality_slots)
    if key is not None:
        with _LOCK:
            if len(_CACHE_MODALITY) > 64:
                _CACHE_MODALITY.clear()
            _CACHE_MODALITY[key] = result
    return result
