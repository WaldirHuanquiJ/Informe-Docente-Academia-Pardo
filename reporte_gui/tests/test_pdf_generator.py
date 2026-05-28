from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.pdf_generator import _extract_entry_exit_minutes


def test_extract_entry_exit_minutes_uses_last_exit_when_multiple_times():
    pair = _extract_entry_exit_minutes("07:00\n09:00\n11:00")
    assert pair == (7 * 60, 11 * 60)
