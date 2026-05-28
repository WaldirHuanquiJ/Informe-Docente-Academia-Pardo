from __future__ import annotations

import csv
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from app.services.logging_config import get_logger

logger = get_logger(__name__)


def _export_with_xlrd(
    xls_path: Path,
    out_csv_path: Path,
    sheet_name: str = "Reporte de Asistencia",
) -> bool:
    try:
        import xlrd  # type: ignore
    except Exception:
        logger.warning("xlrd no está instalado, no se puede usar exportación nativa XLS.")
        return False

    try:
        book = xlrd.open_workbook(str(xls_path))
        sheet = book.sheet_by_name(sheet_name)
    except Exception as exc:
        logger.warning("No se pudo abrir '%s' con xlrd: %s", xls_path.name, exc)
        return False

    out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out_csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
            for r in range(sheet.nrows):
                row_out: list[str] = []
                for c in range(sheet.ncols):
                    cell = sheet.cell(r, c)
                    value = cell.value
                    text = ""
                    if cell.ctype == xlrd.XL_CELL_EMPTY:
                        text = ""
                    elif cell.ctype == xlrd.XL_CELL_TEXT:
                        text = str(value)
                    elif cell.ctype == xlrd.XL_CELL_NUMBER:
                        if float(value).is_integer():
                            text = str(int(value))
                        else:
                            text = str(value)
                    elif cell.ctype == xlrd.XL_CELL_DATE:
                        try:
                            dt = xlrd.xldate.xldate_as_datetime(value, book.datemode)
                            # Si es solo hora (base excel), preferimos HH:MM.
                            if dt.date() <= datetime(1900, 1, 2).date():
                                text = dt.strftime("%H:%M")
                            else:
                                text = dt.strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            text = str(value)
                    elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                        text = "1" if bool(value) else "0"
                    else:
                        text = str(value)
                    row_out.append(text)
                writer.writerow(row_out)
    except Exception as exc:
        logger.error("Error al escribir CSV desde xlrd: %s", exc)
        return False
    return out_csv_path.exists() and out_csv_path.stat().st_size > 0


def export_report_sheet_to_csv(
    xls_path: Path,
    out_csv_path: Path,
    sheet_name: str = "Reporte de Asistencia",
) -> bool:
    if _export_with_xlrd(xls_path, out_csv_path, sheet_name):
        return True

    xls_path = xls_path.resolve()
    out_csv_path = out_csv_path.resolve()
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Lee hoja XLS via OLEDB (ACE) y exporta CSV delimitado por ';' en UTF-8.
    ps_script = rf"""
$ErrorActionPreference = 'Stop'
$xlsPath = '{str(xls_path).replace("'", "''")}'
$outPath = '{str(out_csv_path).replace("'", "''")}'
$sheet = '{sheet_name.replace("'", "''")}$'
$connStr = "Provider=Microsoft.ACE.OLEDB.12.0;Data Source=$xlsPath;Extended Properties='Excel 8.0;HDR=No;IMEX=1';"
$conn = New-Object System.Data.OleDb.OleDbConnection($connStr)
$conn.Open()
$cmd = $conn.CreateCommand()
$cmd.CommandText = "SELECT * FROM [$sheet]"
$adapter = New-Object System.Data.OleDb.OleDbDataAdapter($cmd)
$dt = New-Object System.Data.DataTable
[void]$adapter.Fill($dt)
$conn.Close()

$lines = New-Object System.Collections.Generic.List[string]
foreach ($row in $dt.Rows) {{
    $cells = New-Object System.Collections.Generic.List[string]
    foreach ($col in $dt.Columns) {{
        $v = $row[$col.ColumnName]
        if ($null -eq $v) {{ $txt = '' }} else {{ $txt = [string]$v }}
        $txt = $txt -replace '"','""'
        $cells.Add('"' + $txt + '"')
    }}
    $lines.Add(($cells -join ';'))
}}
[System.IO.File]::WriteAllLines($outPath, $lines, [System.Text.Encoding]::UTF8)
"""

    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        logger.error("Error al ejecutar PowerShell para exportar '%s': %s", xls_path.name, exc)
        return False

    if proc.returncode != 0:
        logger.warning("PowerShell falló (código %d) al exportar '%s': %s",
                       proc.returncode, xls_path.name, proc.stderr.strip())

    return proc.returncode == 0 and out_csv_path.exists() and out_csv_path.stat().st_size > 0


def resolve_report_csv(data_dir: Path) -> Path | None:
    """Resuelve fuente de reporte priorizando cobertura de dias y recencia."""
    xls_candidates = sorted(data_dir.glob("*.xls"))
    out_csv = data_dir / "_runtime_report.csv"
    candidate_paths: list[Path] = []

    for xls in xls_candidates:
        logger.info("Intentando convertir XLS: %s", xls.name)
        if export_report_sheet_to_csv(xls, out_csv):
            logger.info("XLS convertido exitosamente: %s -> %s", xls.name, out_csv.name)
            candidate_paths.append(out_csv)
        else:
            logger.warning("Fallo la conversion de: %s", xls.name)

    fallback_csv = data_dir / "Libro1.csv"
    if fallback_csv.exists():
        logger.info("Usando CSV manual de fallback: %s", fallback_csv.name)
        candidate_paths.append(fallback_csv)

    if candidate_paths:
        try:
            from app.services.report_parser import parse_report
            scored: list[tuple[int, float, Path]] = []
            for p in candidate_paths:
                try:
                    report = parse_report(p)
                    day_count = len(report.days)
                except Exception:
                    day_count = 0
                mtime = p.stat().st_mtime if p.exists() else 0.0
                scored.append((day_count, mtime, p))
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
            picked = scored[0][2]
            logger.info("Fuente seleccionada: %s (dias=%s)", picked.name, scored[0][0])
            return picked
        except Exception:
            if fallback_csv.exists():
                return fallback_csv
            return candidate_paths[0]

    logger.warning("No se encontro ninguna fuente de reporte en %s", data_dir)
    return None