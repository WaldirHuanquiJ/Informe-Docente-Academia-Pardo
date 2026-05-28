from __future__ import annotations

from app.models import TeacherRecord
from app.services.schedule_utils import norm_name


def build_schedule_teachers_from_slots(
    schedule_slots: dict[str, dict[int, set[int]]],
) -> list[TeacherRecord]:
    out: list[TeacherRecord] = []
    seen: set[str] = set()
    for tkey in schedule_slots.keys():
        if "||" not in tkey:
            continue
        alias_key, dept_key = tkey.split("||", maxsplit=1)
        key = f"{alias_key}||{dept_key}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            TeacherRecord(
                teacher_id="-",
                name=alias_key.upper(),
                department=dept_key.upper(),
                marks={},
            )
        )
    return out


def merge_report_with_schedule_teachers(
    csv_teachers: list[TeacherRecord],
    schedule_teachers: list[TeacherRecord],
) -> list[TeacherRecord]:
    merged: list[TeacherRecord] = list(csv_teachers)
    existing = {f"{norm_name(t.name)}||{norm_name(t.department)}" for t in csv_teachers}
    for sch_teacher in schedule_teachers:
        key = f"{norm_name(sch_teacher.name)}||{norm_name(sch_teacher.department)}"
        if key in existing:
            continue
        merged.append(sch_teacher)
        existing.add(key)
    return merged


def teacher_matches_any_alias_set(teacher_name: str, aliases_by_dept: dict[str, set[str]]) -> bool:
    tokens = [norm_name(t) for t in (teacher_name or "").split() if t.strip()]
    if not tokens:
        return False
    alias_union: set[str] = set()
    for alias_set in aliases_by_dept.values():
        alias_union.update(alias_set)
    for token in tokens:
        if token in alias_union:
            return True
    for alias in alias_union:
        alias_tokens = [tok for tok in alias.split() if tok]
        if any(token in alias_tokens for token in tokens):
            return True
    return False
