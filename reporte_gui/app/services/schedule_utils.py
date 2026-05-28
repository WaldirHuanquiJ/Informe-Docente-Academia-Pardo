from __future__ import annotations

import re
import unicodedata

# ── Constantes compartidas ──────────────────────────────────────────────────
HEADER_NAMES = ["HORA", "LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]

TIME_SLOTS = [
    "07:00 - 09:00",
    "09:00 - 11:00",
    "11:00 - 13:00",
    "13:00 - 14:00",
    "14:00 - 16:00",
    "16:00 - 18:00",
    "18:00 - 20:00",
]

SLOT_START_MINUTES = [7 * 60, 9 * 60, 11 * 60, 13 * 60, 14 * 60, 16 * 60, 18 * 60]

_SLOT_RE = re.compile(r"\s+")
_BREAK_RE = re.compile(r"DESCAN[DS]O(?:\s+TARDE)?", re.IGNORECASE)


# ── Funciones de normalización ──────────────────────────────────────────────

def norm_name(text: str) -> str:
    """Normaliza un nombre o alias: sin tildes, sin caracteres especiales, mayúsculas."""
    base = unicodedata.normalize("NFD", text or "")
    base = "".join(ch for ch in base if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9 ]+", " ", base.upper()).strip()


def norm(text: str) -> str:
    """Normaliza texto de cabeceras o slots: colapsa espacios, mayúsculas."""
    return _SLOT_RE.sub(" ", (text or "").strip().upper())


# ── Extracción de horarios ──────────────────────────────────────────────────

def extract_schedule_blocks(rows: list[list[str]]) -> list[tuple[list[str], list[list[str]]]]:
    """Extrae los bloques de horario de una hoja, detectando cabeceras y slots.

    Retorna una lista de tuplas (headers, schedule_rows).
    """
    normalized_headers = [norm(x) for x in HEADER_NAMES]
    header_indices: list[int] = []

    for idx, row in enumerate(rows):
        current = [norm(c) for c in row[:8]]
        if len(current) >= 8 and current[:8] == normalized_headers:
            header_indices.append(idx)

    if not header_indices:
        return [(HEADER_NAMES, [[""] * 8 for _ in TIME_SLOTS])]

    slot_map = {norm(slot): slot for slot in TIME_SLOTS}
    blocks: list[tuple[list[str], list[list[str]]]] = []

    for pos, header_idx in enumerate(header_indices):
        next_header = header_indices[pos + 1] if pos + 1 < len(header_indices) else len(rows)
        section_rows = rows[header_idx + 1 : next_header]

        collected: dict[str, list[str]] = {}
        for row in section_rows:
            if not row:
                continue
            first = norm(row[0] if len(row) > 0 else "")
            if first in slot_map:
                values = (row + [""] * 8)[:8]
                values = [("" if _BREAK_RE.search(norm(v)) else v) for v in values]
                values[0] = slot_map[first]
                collected[first] = values
            if len(collected) == len(TIME_SLOTS):
                break

        ordered_rows: list[list[str]] = []
        for slot in TIME_SLOTS:
            key = norm(slot)
            ordered_rows.append(collected.get(key, [slot, "", "", "", "", "", "", ""]))
        blocks.append((HEADER_NAMES, ordered_rows))

    return blocks if blocks else [(HEADER_NAMES, [[""] * 8 for _ in TIME_SLOTS])]


def extract_schedule_blocks_with_continuity(rows: list[list[str]]) -> list[tuple[list[str], list[list[str]]]]:
    """Versión para HorarioView que soporta filas de continuidad sin hora en col 0."""
    normalized_headers = [norm(x) for x in HEADER_NAMES]
    header_indices: list[int] = []

    for idx, row in enumerate(rows):
        current = [norm(c) for c in row[:8]]
        if len(current) >= 8 and current[:8] == normalized_headers:
            header_indices.append(idx)

    if not header_indices:
        return [(HEADER_NAMES, [[""] * 8 for _ in TIME_SLOTS])]

    slot_map = {norm(slot): slot for slot in TIME_SLOTS}
    blocks: list[tuple[list[str], list[list[str]]]] = []

    for pos, header_idx in enumerate(header_indices):
        next_header = header_indices[pos + 1] if pos + 1 < len(header_indices) else len(rows)
        section_rows = rows[header_idx + 1 : next_header]

        collected: dict[str, list[str]] = {}
        current_slot_key: str | None = None
        for row in section_rows:
            if not row:
                continue
            first = norm(row[0] if len(row) > 0 else "")
            if first in slot_map:
                values = (row + [""] * 8)[:8]
                values = [("" if _BREAK_RE.search(norm(v)) else v) for v in values]
                values[0] = slot_map[first]
                collected[first] = values
                current_slot_key = first
                continue

            # Filas de continuidad (sin hora en col 0): pertenecen al último bloque horario.
            if current_slot_key and not first:
                base = collected.get(current_slot_key)
                if not base:
                    continue
                values = (row + [""] * 8)[:8]
                values = [("" if _BREAK_RE.search(norm(v)) else v) for v in values]
                for c in range(1, 8):
                    extra = (values[c] or "").strip()
                    if not extra:
                        continue
                    prev = (base[c] or "").strip()
                    base[c] = f"{prev}\n{extra}" if prev else extra

        ordered_rows: list[list[str]] = []
        for slot in TIME_SLOTS:
            key = norm(slot)
            ordered_rows.append(collected.get(key, [slot, "", "", "", "", "", "", ""]))
        blocks.append((HEADER_NAMES, ordered_rows))

    return blocks if blocks else [(HEADER_NAMES, [[""] * 8 for _ in TIME_SLOTS])]


# ── Funciones de slots horarios ─────────────────────────────────────────────

def slot_start_minutes(slot_label: str) -> int | None:
    """Extrae los minutos desde medianoche del inicio de un slot tipo '07:00 - 09:00'."""
    raw = (slot_label or "").strip()
    if "-" not in raw:
        return None
    try:
        start = raw.split("-", 1)[0].strip()
        h, m = [int(x) for x in start.split(":")]
        return h * 60 + m
    except (ValueError, IndexError):
        return None


def slot_index_for_label(slot_label: str) -> int | None:
    """Retorna el índice del TIME_SLOTS que corresponde al label dado."""
    start = slot_start_minutes(slot_label)
    if start is None:
        return None
    for idx, ref in enumerate(SLOT_START_MINUTES):
        if ref == start:
            return idx
    return None


def slot_indexes_for_label(slot_label: str) -> list[int]:
    """Retorna todos los indices de slots cubiertos por un label de rango.

    Ejemplos:
    - "13:00 - 14:00" -> [3]
    - "13:00 - 15:00" -> [3, 4]
    - "14:00 - 16:00" -> [4]
    """
    raw = (slot_label or "").strip()
    parts = raw.split("-")
    if len(parts) != 2:
        idx = slot_index_for_label(slot_label)
        return [idx] if idx is not None else []
    try:
        sh, sm = [int(x) for x in parts[0].strip().split(":")]
        eh, em = [int(x) for x in parts[1].strip().split(":")]
        label_start = sh * 60 + sm
        label_end = eh * 60 + em
    except (ValueError, IndexError):
        idx = slot_index_for_label(slot_label)
        return [idx] if idx is not None else []

    if label_end <= label_start:
        idx = slot_index_for_label(slot_label)
        return [idx] if idx is not None else []

    covered: list[int] = []
    for idx in range(len(TIME_SLOTS)):
        bounds = slot_bounds_minutes(idx)
        if bounds is None:
            continue
        slot_start, slot_end = bounds
        overlap_start = max(label_start, slot_start)
        overlap_end = min(label_end, slot_end)
        if overlap_end > overlap_start:
            covered.append(idx)
    if covered:
        return covered

    idx = slot_index_for_label(slot_label)
    return [idx] if idx is not None else []


def slot_bounds_minutes(slot_idx: int) -> tuple[int, int] | None:
    """Retorna (inicio_minutos, fin_minutos) para un índice de TIME_SLOTS."""
    if not (0 <= slot_idx < len(TIME_SLOTS)):
        return None
    slot = TIME_SLOTS[slot_idx]
    parts = slot.split("-")
    if len(parts) != 2:
        return None
    try:
        sh, sm = [int(x) for x in parts[0].strip().split(":")]
        eh, em = [int(x) for x in parts[1].strip().split(":")]
        return sh * 60 + sm, eh * 60 + em
    except (ValueError, IndexError):
        return None


def slot_duration_seconds(slot_idx: int) -> int:
    """Duración en segundos de un slot horario."""
    try:
        parts = TIME_SLOTS[slot_idx].split("-")
        sh, sm = [int(x) for x in parts[0].strip().split(":")]
        eh, em = [int(x) for x in parts[1].strip().split(":")]
        return max(((eh * 60 + em) - (sh * 60 + sm)) * 60, 0)
    except (ValueError, IndexError):
        return 0


def slot_index_for_block(block_text: str) -> int | None:
    """Determina a qué slot horario pertenece un bloque de texto con marcas."""
    match = re.search(r"([01]?\d|2[0-3]):([0-5]\d)", block_text or "")
    if not match:
        return None
    entry = int(match.group(1)) * 60 + int(match.group(2))
    for idx, slot in enumerate(TIME_SLOTS):
        parts = slot.split("-")
        if len(parts) != 2:
            continue
        sh, sm = [int(x) for x in parts[0].strip().split(":")]
        eh, em = [int(x) for x in parts[1].strip().split(":")]
        if (sh * 60 + sm) <= entry < (eh * 60 + em):
            return idx
    return None


# ── Funciones de docentes y horarios ────────────────────────────────────────

def extract_course_and_alias(cell_text: str) -> tuple[str, str]:
    """Extrae curso y alias de una celda de horario 'CURSO ALIAS'."""
    raw = " ".join((cell_text or "").strip().split())
    if not raw:
        return "", ""
    parts = raw.split(" ", 1)
    if len(parts) == 1:
        return parts[0].strip(), ""
    return parts[0].strip(), parts[1].strip()


def extract_course_alias_pairs(cell_text: str) -> list[tuple[str, str]]:
    """Extrae pares (curso, alias) desde una celda, soportando multilinea."""
    raw = (cell_text or "").strip()
    if not raw:
        return []

    line_parts = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(line_parts) >= 2:
        pairs: list[tuple[str, str]] = []
        idx = 0
        while idx + 1 < len(line_parts):
            course = line_parts[idx]
            alias = line_parts[idx + 1]
            if course and alias:
                pairs.append((course, alias))
            idx += 2
        if pairs:
            return pairs

    course, alias = extract_course_and_alias(raw)
    if course and alias:
        return [(course, alias)]
    return []


def teacher_schedule_keys(teacher_id: str, teacher_name: str, department: str) -> list[str]:
    """Genera las claves de búsqueda para un docente en el diccionario de slots."""
    dept_key = norm_name(department)
    tokens = [norm_name(t) for t in teacher_name.split() if t.strip()]
    return [f"{token}||{dept_key}" for token in tokens]


def scheduled_slots_for_teacher_weekday(
    teacher_id: str,
    teacher_name: str,
    department: str,
    schedule_slots: dict[str, dict[int, set[int]]],
    weekday: int,
) -> set[int]:
    """Retorna los slots programados para un docente en un día de la semana."""
    merged: set[int] = set()
    exact_keys = teacher_schedule_keys(teacher_id, teacher_name, department)
    for key in exact_keys:
        merged.update(schedule_slots.get(key, {}).get(weekday, set()))
    if merged:
        return merged

    dept_key = norm_name(department)
    name_tokens = [norm_name(t) for t in teacher_name.split() if t.strip()]
    for key, by_weekday in schedule_slots.items():
        if "||" not in key:
            continue
        alias_part, key_dept = key.split("||", maxsplit=1)
        if key_dept != dept_key:
            continue
        alias_tokens = [tok for tok in alias_part.split() if tok]
        if any(token in alias_tokens for token in name_tokens):
            merged.update(by_weekday.get(weekday, set()))
    return merged


def teacher_exists_in_schedule(
    teacher_name: str,
    department: str,
    aliases_by_dept: dict[str, set[str]],
) -> bool:
    """Verifica si un docente tiene coincidencia en el horario."""
    dept_key = norm_name(department)
    aliases = aliases_by_dept.get(dept_key, set())
    if not aliases:
        return False
    tokens = [norm_name(t) for t in teacher_name.split() if t.strip()]
    if any(token in aliases for token in tokens):
        return True
    for alias in aliases:
        alias_tokens = [tok for tok in alias.split() if tok]
        if any(token in alias_tokens for token in tokens):
            return True
    return False


# ── Utilidades generales ────────────────────────────────────────────────────

def format_hm(total_seconds: int) -> str:
    """Formatea segundos a HH:MM."""
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours:02d}:{minutes:02d}"


def first_time_minutes(text: str) -> int | None:
    """Extrae la primera hora en minutos desde el texto (ej: '08:30' -> 510)."""
    match = re.search(r"([01]?\d|2[0-3]):([0-5]\d)", text or "")
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))
