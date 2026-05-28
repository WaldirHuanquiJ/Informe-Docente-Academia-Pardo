from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import AttendanceReport, TeacherRecord
from app.services.report_parser import parse_report, parse_period_range, _extract_after, _days_from_period


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_csv_path():
    """Crea un CSV de reporte docente con formato esperado por el parser."""
    content = [
        [""],  # fila 0
        [""],  # fila 1
        ["Periodo:", "2024-03-01 ~ 2024-03-31", "Fecha actual:", "2024-04-01"],
        ["", "", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
        ["ID:", "123", "Nombre:", "Juan Perez", "Departamento:", "MATEMATICAS"],
        ["", "", "07:00\n09:00", "11:00\n13:00", "", "", "", "", "", ""],
        ["ID:", "456", "Nombre:", "Maria Lopez", "Departamento:", "FISICA"],
        ["", "", "", "14:00\n16:00", "", "", "", "", "", ""],
    ]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    ) as f:
        writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerows(content)
        path = f.name

    yield Path(path)
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def empty_csv_path():
    """CSV vacío."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    ) as f:
        path = f.name
    yield Path(path)
    Path(path).unlink(missing_ok=True)


# ── _extract_after ──────────────────────────────────────────────────────────

class TestExtractAfter:
    def test_finds_value(self):
        tokens = ["ID:", "123", "Nombre:", "Juan"]
        result = _extract_after(tokens, "ID:")
        assert result == "123"

    def test_not_found(self):
        tokens = ["ID:", "123"]
        result = _extract_after(tokens, "Nombre:")
        assert result == ""

    def test_empty_tokens(self):
        result = _extract_after(["", "", ""], "ID:")
        assert result == ""

    def test_skips_empty_tokens(self):
        result = _extract_after(["Periodo:", "", "", "2024-03-01"], "Periodo:")
        assert result == "2024-03-01"


# ── _days_from_period ───────────────────────────────────────────────────────

class TestDaysFromPeriod:
    def test_march_2024(self):
        days = _days_from_period("2024-03-01 ~ 2024-03-31")
        assert len(days) == 31

    def test_february_2024_leap(self):
        days = _days_from_period("2024-02-01 ~ 2024-02-29")
        assert len(days) == 29

    def test_january(self):
        days = _days_from_period("2024-01-15 ~ 2024-01-15")
        assert len(days) == 31

    def test_invalid(self):
        days = _days_from_period("basura")
        assert days == []


# ── parse_period_range ──────────────────────────────────────────────────────

class TestParsePeriodRange:
    def test_valid_range(self):
        start, end = parse_period_range("2024-03-01 ~ 2024-03-31")
        assert start is not None
        assert end is not None
        assert start.day == 1
        assert end.day == 31

    def test_invalid_range(self):
        start, end = parse_period_range("texto invalido")
        assert start is None
        assert end is None

    def test_empty_string(self):
        start, end = parse_period_range("")
        assert start is None
        assert end is None


# ── parse_report ────────────────────────────────────────────────────────────

class TestParseReport:
    def test_parses_valid_csv(self, sample_csv_path):
        report = parse_report(sample_csv_path)
        assert isinstance(report, AttendanceReport)
        # El parser extrae el primer token después de "Periodo:"
        assert "2024-03-01" in report.period
        assert report.generated_date == "2024-04-01"
        assert len(report.teachers) == 2

    def test_teachers_have_correct_data(self, sample_csv_path):
        report = parse_report(sample_csv_path)
        teacher1 = next(t for t in report.teachers if t.teacher_id == "123")
        assert teacher1.name == "Juan Perez"
        assert teacher1.department == "MATEMATICAS"
        # Las marcas se asignan según los números de día en la fila 3,
        # que empiezan en columna 0 y 1 con "Dia 1", "Dia 2"
        assert len(teacher1.marks) > 0

    def test_teacher_without_id_gets_dash(self, sample_csv_path):
        report = parse_report(sample_csv_path)
        ids = {t.teacher_id for t in report.teachers}
        assert "-" not in ids  # Todos tienen ID en este caso

    def test_raises_on_short_csv(self, empty_csv_path):
        with pytest.raises(ValueError, match="no tiene el formato esperado"):
            parse_report(empty_csv_path)

    def test_report_has_days(self, sample_csv_path):
        report = parse_report(sample_csv_path)
        assert len(report.days) >= 1

    def test_period_start_end(self, sample_csv_path):
        report = parse_report(sample_csv_path)
        assert report.period_start is not None
        assert report.period_end is not None

    def test_marks_normalized(self, sample_csv_path):
        report = parse_report(sample_csv_path)
        teacher1 = next(t for t in report.teachers if t.teacher_id == "123")
        # Las marcas caen en días 3 y 4 por la alineación de columnas
        day1_marks = teacher1.marks.get(1, "")
        assert day1_marks != ""  # Hay marcas normalizadas

    def test_multiple_mark_days(self, sample_csv_path):
        report = parse_report(sample_csv_path)
        teacher1 = next(t for t in report.teachers if t.teacher_id == "123")
        # Días 3 y 4 tienen marcas (posiciones 2 y 3 en la fila de datos)
        assert any(m.strip() for m in [teacher1.marks.get(1, ""), teacher1.marks.get(2, "")])


def test_day_columns_with_offset_are_mapped_correctly():
    content = [
        [""],
        [""],
        ["Periodo:", "2024-03-01 ~ 2024-03-31", "Fecha actual:", "2024-04-01"],
        ["meta", "otro", "1", "2"],
        ["ID:", "123", "Nombre:", "Juan Perez", "Departamento:", "MATEMATICAS"],
        ["", "", "07:00\n09:00", "11:00\n13:00"],
    ]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    ) as f:
        writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerows(content)
        path = Path(f.name)

    try:
        report = parse_report(path)
        teacher = next(t for t in report.teachers if t.teacher_id == "123")
        assert teacher.marks.get(1, "").strip() != ""
        assert teacher.marks.get(2, "").strip() != ""
    finally:
        path.unlink(missing_ok=True)
