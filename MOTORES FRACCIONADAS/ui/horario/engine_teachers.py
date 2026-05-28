from __future__ import annotations

import re
import unicodedata

from app.models import TeacherRecord
from app.services.schedule_utils import HEADER_NAMES, TIME_SLOTS, extract_schedule_blocks_with_continuity


def build_global_teacher_index(view) -> None:
    view._teacher_by_key = {view._teacher_key(t): t for t in view._teachers}
    view._teacher_course_map = {k: set() for k in view._teacher_by_key}
    view._teacher_global_cells = {k: {} for k in view._teacher_by_key}
    view._teacher_global_hours = {k: 0.0 for k in view._teacher_by_key}
    view._teacher_group_hours = {k: {} for k in view._teacher_by_key}

    if not view._workbook or not view._teachers:
        if not view._workbook:
            return

    for sheet_idx, sheet in enumerate(view._workbook.sheets):
        blocks = extract_schedule_blocks_with_continuity(sheet.rows)
        for block_idx, (_, schedule_rows) in enumerate(blocks):
            turno_name = "Manana" if len(blocks) == 1 or block_idx == 0 else ("Tarde" if block_idx == 1 else f"T{block_idx+1}")
            variants = view._sheet_variants_for_name(sheet.name)
            for variant in variants:
                projected_rows = view._project_schedule_rows(schedule_rows, variant)
                view_name = view._sheet_view_name(sheet.name, variant)

                for r, row in enumerate(projected_rows):
                    for c in range(1, min(len(row), 8)):
                        text = (row[c] or "").strip()
                        if not text:
                            continue
                        pairs = view._extract_course_alias_pairs(text)
                        if not pairs:
                            continue

                        for course, alias_candidates in pairs:
                            if not alias_candidates:
                                continue
                            pair_target_keys: set[str] = set()
                            for alias in alias_candidates:
                                matched_this_alias = False
                                for teacher in view._teachers:
                                    key_teacher = view._teacher_key(teacher)
                                    aliases = view._teacher_aliases(teacher.name)
                                    if not view._alias_matches_teacher(alias, aliases):
                                        continue
                                    if course and view._tchr_norm_name(course) != view._tchr_norm_name(teacher.department):
                                        continue
                                    pair_target_keys.add(key_teacher)
                                    matched_this_alias = True

                                if not matched_this_alias:
                                    skey = view._schedule_teacher_key(alias, course)
                                    if skey not in view._teacher_by_key:
                                        view._teacher_by_key[skey] = TeacherRecord(
                                            teacher_id="-",
                                            name=alias.upper(),
                                            department=(course.upper() if course else "(SIN CURSO)"),
                                            marks={},
                                        )
                                        view._teacher_course_map[skey] = set()
                                        view._teacher_global_cells[skey] = {}
                                        view._teacher_global_hours[skey] = 0.0
                                        view._teacher_group_hours[skey] = {}
                                    pair_target_keys.add(skey)

                            for key_teacher in pair_target_keys:
                                if course:
                                    view._teacher_course_map.setdefault(key_teacher, set()).add(course)
                                key = (r, c)
                                src = f"{course} [{view_name}/{turno_name}]".strip()
                                view._teacher_global_cells.setdefault(key_teacher, {}).setdefault(key, []).append(src)
                                slot_h = view._slot_hours(TIME_SLOTS[r])
                                view._teacher_global_hours[key_teacher] = view._teacher_global_hours.get(key_teacher, 0.0) + slot_h
                                view._teacher_group_hours.setdefault(key_teacher, {})
                                view._teacher_group_hours[key_teacher][view_name] = (
                                    view._teacher_group_hours[key_teacher].get(view_name, 0.0) + slot_h
                                )


def extract_course_alias_pairs(view, cell_text: str) -> list[tuple[str, list[str]]]:
    raw = (cell_text or "").strip()
    if not raw:
        return []

    line_parts = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    paired_parts: list[str] = []
    if len(line_parts) >= 2:
        idx = 0
        while idx + 1 < len(line_parts):
            paired_parts.append(f"{line_parts[idx]} {line_parts[idx + 1]}")
            idx += 2
        if idx < len(line_parts):
            paired_parts.append(line_parts[idx])

    parts = [p.strip() for p in view._PAIR_SPLIT_RE.split(raw) if p.strip()]
    if paired_parts:
        parts = paired_parts
    if not parts:
        parts = [raw]

    pairs: list[tuple[str, list[str]]] = []
    for part in parts:
        compact = " ".join(part.split())
        if " " not in compact:
            continue
        tokens = compact.split()
        current_course = tokens[0].strip()
        alias_tokens: list[str] = []

        def flush_pair(course_value: str, alias_parts: list[str]) -> None:
            alias_raw_inner = " ".join(alias_parts).strip()
            if not course_value or not alias_raw_inner:
                return
            aliases: list[str] = [alias_raw_inner]
            for piece in view._ALIAS_SPLIT_RE.split(alias_raw_inner):
                clean = piece.strip()
                if clean:
                    aliases.append(clean)
            unique: list[str] = []
            seen: set[str] = set()
            for alias in aliases:
                key = view._tchr_norm_name(alias)
                if key and key not in seen:
                    seen.add(key)
                    unique.append(alias)
            if unique:
                pairs.append((course_value.strip(), unique))

        for tk in tokens[1:]:
            tk_norm = view._tchr_norm_name(tk)
            if alias_tokens and tk_norm in view._known_courses_norm:
                flush_pair(current_course, alias_tokens)
                current_course = tk
                alias_tokens = []
            else:
                alias_tokens.append(tk)

        flush_pair(current_course, alias_tokens)
    return pairs


def tchr_norm_name(text: str) -> str:
    base = unicodedata.normalize("NFD", text or "")
    base = "".join(ch for ch in base if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9 ]+", " ", base.upper()).strip()


def slot_hours(_view, slot_label: str) -> float:
    parts = slot_label.split("-")
    if len(parts) != 2:
        return 0.0
    try:
        h1, m1 = [int(x) for x in parts[0].strip().split(":")]
        h2, m2 = [int(x) for x in parts[1].strip().split(":")]
        return max(((h2 * 60 + m2) - (h1 * 60 + m1)) / 60.0, 0.0)
    except Exception:
        return 0.0


def build_daily_hours_summary_items(view, schedule_rows: list[list[str]]) -> list[str]:
    day_names = HEADER_NAMES[1:]
    day_hours = [0.0] * 7
    for row in schedule_rows:
        hours = view._slot_hours(row[0] if row else "")
        for day_idx in range(1, min(8, len(row))):
            if (row[day_idx] or "").strip():
                day_hours[day_idx - 1] += hours
    weekly_total = sum(day_hours)
    items = [f"{day_names[i]}: {day_hours[i]:.1f} h" for i in range(7)]
    items.append(f"TOTAL SEMANA: {weekly_total:.1f} h")
    return items


def build_group_hours_summary_items(view, schedule_rows: list[list[str]]) -> list[str]:
    day_names = HEADER_NAMES[1:]
    day_hours = [0.0] * 7
    for row in schedule_rows:
        hours = view._slot_hours(row[0] if row else "")
        for day_idx in range(1, min(8, len(row))):
            if (row[day_idx] or "").strip():
                day_hours[day_idx - 1] += hours
    weekly_total = sum(day_hours)
    items = [f"{day_names[i]}: {day_hours[i]:.1f} h" for i in range(7)]
    items.append(f"TOTAL GRUPO: {weekly_total:.1f} h")
    return items
