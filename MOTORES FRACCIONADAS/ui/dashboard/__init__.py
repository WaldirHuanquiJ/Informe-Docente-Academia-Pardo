from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_pkg_dir = Path(__file__).resolve().parent
_file_module_path = _pkg_dir.parent / "dashboard.py"
_spec = importlib.util.spec_from_file_location("app.ui._dashboard_file", _file_module_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"No se pudo cargar dashboard.py desde {_file_module_path}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("app.ui._dashboard_file", _mod)
_spec.loader.exec_module(_mod)

DashboardView = _mod.DashboardView

__all__ = ["DashboardView"]
