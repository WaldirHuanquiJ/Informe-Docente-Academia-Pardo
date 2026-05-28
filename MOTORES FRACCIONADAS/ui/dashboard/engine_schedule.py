from __future__ import annotations

from app.models import TeacherRecord
from app.services.horario_excel import load_horarios_workbook
from app.services.schedule_rules_cache import get_basic_rules
from app.services.schedule_versions import resolve_schedule_for_date
from app.services.schedule_utils import extract_course_alias_pairs, extract_schedule_blocks_with_continuity, norm_name
from app.services.logging_config import get_logger

logger = get_logger(__name__)


def load_schedule_rules(view) -> None:
    view._schedule_aliases_by_dept = {}
    view._teacher_schedule_slots = {}
    view._day_schedule_aliases_by_dept = {}
    view._day_teacher_schedule_slots = {}
    view._day_schedule_name = {}
    view._schedule_teachers = []

    teacher_keys: set[str] = set()
    if view.report and view.report.period_start:
        schedule_dir = view._schedule_path.parent
        for day in view.report.days:
            try:
                target_date = view.report.period_start.replace(day=day).date()
            except ValueError:
                continue
            schedule_path = resolve_schedule_for_date(schedule_dir, target_date, view._schedule_path)
            if not schedule_path or not schedule_path.exists():
                continue
            view._day_schedule_name[day] = schedule_path.stem
            aliases, slots = view._extract_rules_from_workbook(schedule_path)
            if aliases:
                view._day_schedule_aliases_by_dept[day] = aliases
            if slots:
                view._day_teacher_schedule_slots[day] = slots
            for dept_key, alias_set in aliases.items():
                view._schedule_aliases_by_dept.setdefault(dept_key, set()).update(alias_set)
            for tkey, by_weekday in slots.items():
                target = view._teacher_schedule_slots.setdefault(tkey, {})
                for weekday, slot_set in by_weekday.items():
                    target.setdefault(weekday, set()).update(slot_set)
            for tkey in slots.keys():
                if tkey in teacher_keys:
                    continue
                teacher_keys.add(tkey)
        view._schedule_teachers = view._build_schedule_teachers_from_slots(view._teacher_schedule_slots)
    elif view._schedule_path.exists():
        aliases, slots = view._extract_rules_from_workbook(view._schedule_path)
        view._schedule_aliases_by_dept = {k: set(v) for k, v in aliases.items()}
        view._teacher_schedule_slots = {k: {w: set(s) for w, s in v.items()} for k, v in slots.items()}
        view._schedule_teachers = view._build_schedule_teachers_from_slots(view._teacher_schedule_slots)
    else:
        logger.info("Archivo de horario no encontrado: %s", view._schedule_path)

    if view._schedule_path.exists():
        try:
            workbook = load_horarios_workbook(view._schedule_path)
        except Exception:
            workbook = None
        if workbook is not None:
            known: set[str] = set()
            for sheet in workbook.sheets:
                for _, schedule_rows in extract_schedule_blocks_with_continuity(sheet.rows):
                    for row in schedule_rows:
                        for day_col in range(1, min(8, len(row))):
                            cell = (row[day_col] or "").strip()
                            if not cell:
                                continue
                            for course, _alias in extract_course_alias_pairs(cell):
                                if course:
                                    known.add(norm_name(course))
            view._known_courses_norm = known


def extract_rules_from_workbook(_view, xlsx_path):
    return get_basic_rules(xlsx_path, continuity=True)


def build_schedule_teachers_from_slots(_view, schedule_slots: dict[str, dict[int, set[int]]]) -> list[TeacherRecord]:
    out: list[TeacherRecord] = []
    for tkey in sorted(schedule_slots.keys()):
        alias_key, dept_key = tkey.split("||", maxsplit=1)
        out.append(TeacherRecord(teacher_id="-", name=alias_key.upper(), department=dept_key.upper(), marks={}))
    return out


def merge_report_with_schedule_teachers(_view, csv_teachers: list[TeacherRecord], schedule_teachers: list[TeacherRecord]) -> list[TeacherRecord]:
    merged: list[TeacherRecord] = list(csv_teachers)
    existing = {f"{t.name.lower()}||{t.department.lower()}" for t in csv_teachers}
    for sch_teacher in schedule_teachers:
        key = f"{sch_teacher.name.lower()}||{sch_teacher.department.lower()}"
        if key not in existing:
            merged.append(sch_teacher)
            existing.add(key)
    return sorted(merged, key=lambda t: (t.name.lower(), t.department.lower(), t.teacher_id))
