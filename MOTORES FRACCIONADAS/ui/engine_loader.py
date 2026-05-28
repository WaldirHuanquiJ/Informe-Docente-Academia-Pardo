from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_ui_engine(ui_file: str, folder: str, module_file: str) -> ModuleType:
    base_dir = Path(ui_file).resolve().parent
    target_path = base_dir / folder / f"{module_file}.py"
    cache_key = f"app.ui._engine_{folder}_{module_file}"
    cached = sys.modules.get(cache_key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(cache_key, target_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar engine: {target_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[cache_key] = module
    spec.loader.exec_module(module)
    return module
