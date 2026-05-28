from __future__ import annotations

import pytest
import sys
from pathlib import Path

# Agregar el directorio padre al path para importar app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.time_rules import (
    normalize_time_marks,
    reconcile_entries_and_exits,
    adjust_continuous_schedule,
    format_time_blocks,
    nearest_allowed_hour,
    rounded_entry_if_close,
    split_cell_blocks,
    compute_seconds_from_mark_text,
    expected_entry_minutes,
    compute_tardiness_seconds_from_mark_text,
    ENTRY_ROUNDING_TOLERANCE_MIN,
    CONTINUOUS_GAP_TOLERANCE_MIN,
)


# ── normalize_time_marks ────────────────────────────────────────────────────

class TestNormalizeTimeMarks:
    def test_empty_string(self):
        assert normalize_time_marks("") == ""

    def test_no_times(self):
        assert normalize_time_marks("Sin marca") == "Sin marca"

    def test_simple_interval(self):
        result = normalize_time_marks("07:00 09:00")
        assert "07:00" in result
        assert "_____" in result

    def test_multiple_intervals(self):
        result = normalize_time_marks("07:00 09:00 11:00 13:00")
        assert result.count("_____") >= 1

    def test_compacted_string(self):
        # La regex TIME_PATTERN requiere ":", así que "0700" sin ":" se devuelve tal cual
        result = normalize_time_marks("0700 0900")
        assert result == "0700 0900"

    def test_with_spaces(self):
        result = normalize_time_marks("  07:00   09:00  ")
        assert "07:00" in result


# ── reconcile_entries_and_exits ─────────────────────────────────────────────

class TestReconcileEntriesAndExits:
    def test_empty_list(self):
        assert reconcile_entries_and_exits([]) == []

    def test_single_time(self):
        result = reconcile_entries_and_exits(["07:00"])
        # Debe generar salida esperada después de la entrada
        assert len(result) >= 2

    def test_pair_of_times(self):
        result = reconcile_entries_and_exits(["07:00", "09:00"])
        assert "07:00" in result

    def test_invalid_time_returns_original(self):
        result = reconcile_entries_and_exits(["25:00", "09:00"])
        assert result == ["25:00", "09:00"]

    def test_triple_times(self):
        result = reconcile_entries_and_exits(["07:00", "09:00", "11:00"])
        # Debe detectar que no es salida válida y completar
        assert len(result) >= 4

    def test_rounded_entry_detection(self):
        # Si la siguiente entrada está cerca de un horario de entrada conocido,
        # debe redondearse
        result = reconcile_entries_and_exits(["07:00", "09:10"])
        # 09:10 está cerca de 09:00 (10 min <= 20 min de tolerancia)
        # pero el expected después de 07:00 es 09:00
        # Si abs(9*60+10 - 9*60) = 10 <= 20, se considera entrada redondeada
        assert len(result) >= 2


# ── adjust_continuous_schedule ──────────────────────────────────────────────

class TestAdjustContinuousSchedule:
    def test_less_than_4(self):
        result = adjust_continuous_schedule(["07:00", "09:00", "11:00"])
        assert result == ["07:00", "09:00", "11:00"]

    def test_no_gap(self):
        result = adjust_continuous_schedule(["07:00", "09:00", "11:00", "13:00"])
        # Hay un gap de 2h entre 09:00 y 11:00, > 20 min
        assert result == ["07:00", "09:00", "11:00", "13:00"]

    def test_small_gap_merged(self):
        # Gap de 5 min entre salida y siguiente entrada: debe fusionarse
        result = adjust_continuous_schedule(["07:00", "09:00", "09:05", "11:00"])
        assert result[2] == "09:00"  # La entrada se iguala a la salida anterior


# ── format_time_blocks ──────────────────────────────────────────────────────

class TestFormatTimeBlocks:
    def test_empty(self):
        assert format_time_blocks([]) == ""

    def test_pair(self):
        result = format_time_blocks(["07:00", "09:00"])
        assert result == "07:00\n09:00"

    def test_four_times(self):
        result = format_time_blocks(["07:00", "09:00", "11:00", "13:00"])
        assert result.count("_____") == 1
        assert "07:00" in result
        assert "13:00" in result


# ── nearest_allowed_hour ────────────────────────────────────────────────────

class TestNearestAllowedHour:
    def test_exact_match(self):
        assert nearest_allowed_hour(9) == 9

    def test_closest(self):
        assert nearest_allowed_hour(10) == 9

    def test_ambiguous(self):
        # 15 está entre 14 y 16, más cerca de 14
        assert nearest_allowed_hour(15) == 14

    def test_high_value(self):
        # 19 está a 1 de 18 y a 1 de 20; min con empate devuelve 18
        result = nearest_allowed_hour(19)
        assert result in (18, 20)


# ── rounded_entry_if_close ──────────────────────────────────────────────────

class TestRoundedEntryIfClose:
    def test_exact_match(self):
        # 420 minutos = 7*60, debe devolver 7
        assert rounded_entry_if_close(7 * 60) == 7

    def test_within_tolerance(self):
        # 430 minutos = 7*60+10, tolerancia 20 min => ok
        result = rounded_entry_if_close(7 * 60 + 10)
        assert result == 7

    def test_outside_tolerance(self):
        # 450 minutos = 7*60+30, > 20 min tolerancia => None
        result = rounded_entry_if_close(7 * 60 + 30)
        assert result is None


# ── split_cell_blocks ───────────────────────────────────────────────────────

class TestSplitCellBlocks:
    def test_empty_string(self):
        result = split_cell_blocks("")
        assert result == [""]

    def test_single_block(self):
        result = split_cell_blocks("07:00\n09:00")
        assert len(result) == 1

    def test_two_blocks(self):
        result = split_cell_blocks("07:00\n09:00_____11:00\n13:00")
        assert len(result) == 2

    def test_trailing_spaces(self):
        result = split_cell_blocks("  07:00\n09:00  ")
        assert len(result) == 1


# ── compute_seconds_from_mark_text ──────────────────────────────────────────

class TestComputeSecondsFromMarkText:
    def test_empty(self):
        assert compute_seconds_from_mark_text("") == 0

    def test_single_interval(self):
        seconds = compute_seconds_from_mark_text("07:00\n09:00")
        assert seconds == 2 * 3600  # 2 horas

    def test_two_intervals(self):
        seconds = compute_seconds_from_mark_text("07:00\n09:00_____11:00\n13:00")
        assert seconds == 4 * 3600  # 4 horas total

    def test_no_times(self):
        assert compute_seconds_from_mark_text("Sin marca") == 0

    def test_negative_delta(self):
        # Caso donde la salida es menor que la entrada (ej: se interpreta como día siguiente)
        seconds = compute_seconds_from_mark_text("23:00\n01:00")
        assert seconds == 2 * 3600  # 2 horas


# ── expected_entry_minutes ──────────────────────────────────────────────────

class TestExpectedEntryMinutes:
    def test_before_first_slot(self):
        # 6:00 = 360 min, no hay slot <= 360
        result = expected_entry_minutes(6 * 60)
        assert result is None

    def test_after_seven(self):
        # 7:30 = 450 min, el slot más cercano es 7:00 = 420
        result = expected_entry_minutes(7 * 60 + 30)
        assert result == 7 * 60

    def test_after_nine(self):
        # 9:30 = 570 min, slot más cercano es 9:00 = 540
        result = expected_entry_minutes(9 * 60 + 30)
        assert result == 9 * 60


# ── compute_tardiness_seconds_from_mark_text ────────────────────────────────

class TestTardinessSeconds:
    def test_empty_text(self):
        assert compute_tardiness_seconds_from_mark_text("") == 0

    def test_no_times(self):
        assert compute_tardiness_seconds_from_mark_text("texto") == 0

    def test_punctual(self):
        tardiness = compute_tardiness_seconds_from_mark_text("07:00\n09:00")
        assert tardiness == 0

    def test_late_by_10_min(self):
        tardiness = compute_tardiness_seconds_from_mark_text("07:10\n09:00")
        assert tardiness == 10 * 60

    def test_late_by_30_min(self):
        tardiness = compute_tardiness_seconds_from_mark_text("07:30\n09:00")
        assert tardiness == 30 * 60

    def test_multiple_entries_with_late_first(self):
        tardiness = compute_tardiness_seconds_from_mark_text("07:15\n09:00_____14:05\n16:00")
        # 07:15: 15 min tarde del slot 07:00
        # 14:05: 5 min tarde del slot 14:00
        assert tardiness == 20 * 60