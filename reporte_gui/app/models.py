from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TeacherRecord:
    teacher_id: str
    name: str
    department: str
    marks: dict[int, str]


@dataclass
class AttendanceReport:
    period: str
    generated_date: str
    days: list[int]
    teachers: list[TeacherRecord]
    period_start: datetime | None
    period_end: datetime | None
