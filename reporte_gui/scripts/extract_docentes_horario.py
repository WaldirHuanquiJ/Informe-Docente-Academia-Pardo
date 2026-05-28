from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys


def _bootstrap_imports() -> None:
    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    pkg_root = repo_root / "reporte_gui"
    if str(pkg_root) not in sys.path:
        sys.path.insert(0, str(pkg_root))


_bootstrap_imports()

from app.services.horario_excel import load_horarios_workbook  # noqa: E402
from app.services.schedule_utils import extract_course_alias_pairs, extract_schedule_blocks_with_continuity  # noqa: E402


def extract_rows(data_dir: Path) -> list[tuple[str, str, str, str]]:
    files = sorted(data_dir.glob("HORARIOS_*.xlsx"))
    rows: list[tuple[str, str, str, str]] = []
    for fpath in files:
        workbook = load_horarios_workbook(fpath)
        for sheet in workbook.sheets:
            blocks = extract_schedule_blocks_with_continuity(sheet.rows)
            for _headers, schedule_rows in blocks:
                for row in schedule_rows:
                    for day_col in range(1, min(8, len(row))):
                        cell = (row[day_col] or "").strip()
                        if not cell:
                            continue
                        for course, alias in extract_course_alias_pairs(cell):
                            course = (course or "").strip()
                            alias = (alias or "").strip()
                            if alias:
                                rows.append((alias, course, fpath.name, sheet.name))
    return rows


def is_noise(name: str) -> bool:
    value = (name or "").strip().upper()
    if not value:
        return True
    blocked = {
        "MODALIDAD:",
        "TARDE",
        "MANANA",
        "MAÑANA",
    }
    return value in blocked


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrae docentes desde archivos HORARIOS_*.xlsx")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data",
        help="Carpeta donde estan los horarios (default: <repo>/data)",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Ruta CSV de salida. Si no se indica, solo imprime en consola.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Excluye etiquetas no-docente conocidas (ej: MODALIDAD:, TARDE).",
    )
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    if not data_dir.exists():
        print(f"ERROR: no existe la carpeta: {data_dir}")
        return 1

    raw_rows = extract_rows(data_dir)
    unique_rows = sorted(set(raw_rows), key=lambda x: (x[0].upper(), x[1].upper(), x[2], x[3]))
    if args.clean:
        unique_rows = [r for r in unique_rows if not is_noise(r[0])]

    unique_teachers = sorted({row[0] for row in unique_rows}, key=lambda s: s.upper())

    print(f"DATA_DIR={data_dir}")
    print(f"TOTAL_DOCENTES_UNICOS={len(unique_teachers)}")
    print(f"TOTAL_PARES_DOCENTE_CURSO={len({(r[0], r[1]) for r in unique_rows})}")
    print(f"TOTAL_REGISTROS={len(unique_rows)}")
    print("---DOCENTES---")
    for teacher in unique_teachers:
        print(teacher)

    if args.output_csv:
        out_path = args.output_csv.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(["docente", "curso", "archivo_horario", "hoja"])
            writer.writerows(unique_rows)
        print(f"CSV={out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
