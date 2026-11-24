from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# Maps NDBC field code -> (event_type, unit)
FIELD_MAP: Dict[str, Tuple[str, str]] = {
    "WDIR": ("wind_direction",          "degrees"),
    "WSPD": ("wind_speed",              "m/s"),
    "GST":  ("wind_gust",               "m/s"),
    "WVHT": ("wave_height",             "m"),
    "DPD":  ("dominant_wave_period",    "s"),
    "APD":  ("average_wave_period",     "s"),
    "MWD":  ("wave_direction",          "degrees"),
    "PRES": ("sea_level_pressure",      "hPa"),
    "ATMP": ("air_temperature",         "degC"),
    "WTMP": ("sea_surface_temperature", "degC"),
    "DEWP": ("dewpoint",                "degC"),
}

MISSING = "MM"  # NDBC sentinel for unavailable measurements


def parse_rows(text: str) -> List[Dict[str, str]]:
    """
    Parse every observation row from NDBC realtime text, newest first.
    Line 0: column headers (prefixed with #)
    Line 1: units row (prefixed with #, skipped)
    Line 2+: observations, newest first (~45 days)
    Rows whose column count doesn't match the header are skipped.
    """
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 3:
        return []
    columns = lines[0].lstrip("#").split()
    rows: List[Dict[str, str]] = []
    for line in lines[2:]:
        values = line.split()
        if len(values) == len(columns):
            rows.append(dict(zip(columns, values)))
    return rows


def parse_latest_row(text: str) -> Optional[Dict[str, str]]:
    """Most recent observation row as raw {column: value}, or None if unparseable."""
    rows = parse_rows(text)
    return rows[0] if rows else None


def extract_measurements(row: Dict[str, str]) -> Dict[str, float]:
    """Return {field_code: float} for all non-missing fields in FIELD_MAP."""
    measurements: Dict[str, float] = {}
    for field in FIELD_MAP:
        raw = row.get(field, MISSING)
        if raw != MISSING:
            try:
                measurements[field] = float(raw)
            except ValueError:
                pass
    return measurements
