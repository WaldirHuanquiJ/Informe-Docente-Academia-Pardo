from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_pkg_dir = Path(__file__).resolve().parent
_file_module_path = _pkg_dir.parent / "horario.py"
_spec = importlib.util.spec_from_file_location("app.ui._horario_file", _file_module_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"No se pudo cargar horario.py desde {_file_module_path}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("app.ui._horario_file", _mod)
_spec.loader.exec_module(_mod)

FlowLayout = _mod.FlowLayout
HorarioView = _mod.HorarioView

__all__ = ["FlowLayout", "HorarioView"]
