from __future__ import annotations

from app.services.biometric_import import export_report_sheet_to_csv, resolve_report_csv
from app.services.horario_excel import WorkbookData, SheetData, load_horarios_workbook
from app.services.logging_config import get_logger, setup_logging
from app.services.report_parser import parse_report, parse_period_range
from app.services.schedule_utils import (
    HEADER_NAMES,
    TIME_SLOTS,
    SLOT_START_MINUTES,
    norm,
    norm_name,
    extract_schedule_blocks,
    extract_schedule_blocks_with_continuity,
    extract_course_and_alias,
    format_hm,
    first_time_minutes,
    scheduled_slots_for_teacher_weekday,
    slot_bounds_minutes,
    slot_duration_seconds,
    slot_index_for_block,
    slot_index_for_label,
    slot_indexes_for_label,
    slot_start_minutes,
    teacher_exists_in_schedule,
    teacher_schedule_keys,
)
from app.services.session_store import load_session, save_session
from app.services.time_rules import (
    compute_seconds_from_mark_text,
    compute_tardiness_seconds_from_mark_text,
    normalize_time_marks,
    split_cell_blocks,
)
from app.services.attendance_engine import (
    AnalysisPolicy,
    DEFAULT_POLICY,
    extract_entry_exit_pairs,
    extract_single_entry_minutes,
    extract_trailing_unpaired_entry_minutes,
    extra_block_metrics,
    extra_planned_window,
    normalize_extra_block_text,
    normalized_event_minutes,
)
from app.services.day_slot_engine import build_day_slot_values
from app.services.weekly_store import get_weekly_hours, set_weekly_hours

__all__ = [
    # biometric_import
    "export_report_sheet_to_csv",
    "resolve_report_csv",
    # horario_excel
    "WorkbookData",
    "SheetData",
    "load_horarios_workbook",
    # logging
    "get_logger",
    "setup_logging",
    # report_parser
    "parse_report",
    "parse_period_range",
    # schedule_utils
    "HEADER_NAMES",
    "TIME_SLOTS",
    "SLOT_START_MINUTES",
    "norm",
    "norm_name",
    "extract_schedule_blocks",
    "extract_schedule_blocks_with_continuity",
    "extract_course_and_alias",
    "format_hm",
    "first_time_minutes",
    "scheduled_slots_for_teacher_weekday",
    "slot_bounds_minutes",
    "slot_duration_seconds",
    "slot_index_for_block",
    "slot_index_for_label",
    "slot_indexes_for_label",
    "slot_start_minutes",
    "teacher_exists_in_schedule",
    "teacher_schedule_keys",
    # session_store
    "load_session",
    "save_session",
    # time_rules
    "compute_seconds_from_mark_text",
    "compute_tardiness_seconds_from_mark_text",
    "normalize_time_marks",
    "split_cell_blocks",
    # attendance_engine
    "AnalysisPolicy",
    "DEFAULT_POLICY",
    "extract_entry_exit_pairs",
    "extract_single_entry_minutes",
    "extract_trailing_unpaired_entry_minutes",
    "extra_block_metrics",
    "extra_planned_window",
    "normalize_extra_block_text",
    "normalized_event_minutes",
    # day_slot_engine
    "build_day_slot_values",
    # weekly_store
    "get_weekly_hours",
    "set_weekly_hours",
]
