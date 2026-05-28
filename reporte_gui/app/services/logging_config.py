from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(log_dir: Path | None = None, level: int = logging.INFO) -> logging.Logger:
    """Configura el sistema de logging con salida a consola y archivo.

    Args:
        log_dir: Directorio donde guardar el archivo de log.
                 Si es None, solo se loguea a consola.
        level: Nivel de logging (default: INFO).

    Returns:
        Logger raíz configurado.
    """
    root_logger = logging.getLogger("reporte_docente")
    root_logger.setLevel(level)

    # Evitar duplicar handlers si ya fue configurado
    if root_logger.handlers:
        return root_logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-7s] %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler de consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Handler de archivo (opcional)
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / "reporte_docente.log",
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Obtiene un logger hijo del logger raíz 'reporte_docente'.

    Args:
        name: Nombre del módulo (usualmente __name__).

    Returns:
        Logger configurado.
    """
    return logging.getLogger(f"reporte_docente.{name}")