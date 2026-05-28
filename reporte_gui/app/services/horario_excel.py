from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/package/2006/relationships",
}
CELL_REF_RE = re.compile(r"([A-Z]+)(\d+)")


@dataclass
class SheetData:
    name: str
    headers: list[str]
    rows: list[list[str]]


@dataclass
class WorkbookData:
    sheets: list[SheetData]


_WB_CACHE_LOCK = RLock()
_WB_CACHE: dict[tuple[str, int, int], WorkbookData] = {}


def _col_to_index(col: str) -> int:
    result = 0
    for ch in col:
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    items: list[str] = []
    for si in root.findall("m:si", NS):
        t = si.find("m:t", NS)
        if t is not None and t.text is not None:
            items.append(t.text)
            continue
        runs = si.findall("m:r", NS)
        combined = "".join((r.find("m:t", NS).text or "") for r in runs if r.find("m:t", NS) is not None)
        items.append(combined)
    return items


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        t = cell.find("m:is/m:t", NS)
        return (t.text or "") if t is not None else ""

    v = cell.find("m:v", NS)
    if v is None or v.text is None:
        return ""

    if cell_type == "s":
        try:
            idx = int(v.text)
            return shared[idx] if 0 <= idx < len(shared) else ""
        except ValueError:
            return ""

    return v.text


def _read_sheet(zf: zipfile.ZipFile, target: str, name: str, shared: list[str]) -> SheetData:
    root = ET.fromstring(zf.read(f"xl/{target}"))
    sheet_data = root.find("m:sheetData", NS)
    if sheet_data is None:
        return SheetData(name=name, headers=[], rows=[])

    max_col = 0
    raw_rows: list[dict[int, str]] = []

    for row in sheet_data.findall("m:row", NS):
        data: dict[int, str] = {}
        for cell in row.findall("m:c", NS):
            ref = cell.attrib.get("r", "")
            match = CELL_REF_RE.match(ref)
            if not match:
                continue
            col_letters = match.group(1)
            col_idx = _col_to_index(col_letters)
            value = _cell_value(cell, shared).strip()
            data[col_idx] = value
            if col_idx > max_col:
                max_col = col_idx
        raw_rows.append(data)

    width = max_col + 1 if max_col >= 0 else 0
    rows: list[list[str]] = []
    for data in raw_rows:
        row = [""] * width
        for idx, value in data.items():
            row[idx] = value
        if any(cell.strip() for cell in row):
            rows.append(row)

    headers = [str(i + 1) for i in range(width)]
    return SheetData(name=name, headers=headers, rows=rows)


def load_horarios_workbook(path: Path) -> WorkbookData:
    resolved = path.resolve()
    try:
        st = resolved.stat()
        cache_key = (str(resolved), int(st.st_mtime_ns), int(st.st_size))
    except Exception:
        cache_key = None

    if cache_key is not None:
        with _WB_CACHE_LOCK:
            cached = _WB_CACHE.get(cache_key)
            if cached is not None:
                return cached

    with zipfile.ZipFile(path) as zf:
        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))

        rel_map = {
            rel.attrib.get("Id", ""): rel.attrib.get("Target", "")
            for rel in rels_root.findall("p:Relationship", NS)
        }
        shared = _read_shared_strings(zf)

        sheets: list[SheetData] = []
        sheets_node = wb_root.find("m:sheets", NS)
        if sheets_node is None:
            return WorkbookData(sheets=[])

        for sheet in sheets_node.findall("m:sheet", NS):
            name = sheet.attrib.get("name", "Hoja")
            rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
            target = rel_map.get(rid, "")
            if not target.startswith("worksheets/"):
                continue
            sheets.append(_read_sheet(zf, target, name, shared))

    result = WorkbookData(sheets=sheets)
    if cache_key is not None:
        with _WB_CACHE_LOCK:
            # Evitar crecimiento infinito en sesiones largas.
            if len(_WB_CACHE) > 24:
                _WB_CACHE.clear()
            _WB_CACHE[cache_key] = result
    return result
