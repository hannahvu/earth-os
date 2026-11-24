"""
Curated list of globally distributed NDBC buoy station IDs and a loader
that fetches their coordinates from the NDBC station metadata table.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, Optional, Tuple

import httpx

STATION_TABLE_URL = "https://www.ndbc.noaa.gov/data/stations/station_table.txt"

# Globally distributed stations covering major ocean basins.
# Coordinates are fetched dynamically from NDBC's station table.
PRIORITY_IDS = [
    # North Atlantic
    "41047", "41048", "41049", "44025", "44013", "44065",
    # Gulf of Mexico
    "42001", "42002", "42003", "42036", "42060",
    # NE Pacific (US West Coast)
    "46047", "46025", "46026", "46059", "46066",
    # Hawaii / Central Pacific
    "51001", "51002", "51003", "51004",
    # South / Tropical Atlantic
    "41041", "41044", "41046",
    # Indian Ocean
    "23003", "23008",
    # South Pacific
    "32012",
    # Bering Sea / North Pacific
    "46035", "46080",
]


def _parse_location(location_str: str) -> Optional[Tuple[float, float]]:
    """Parse '44.794 N 87.313 W ...' -> (lat, lon). Returns None if unparseable."""
    m = re.search(r"([\d.]+)\s+([NS])\s+([\d.]+)\s+([EW])", location_str)
    if not m:
        return None
    lat = float(m.group(1)) * (1 if m.group(2) == "N" else -1)
    lon = float(m.group(3)) * (-1 if m.group(4) == "W" else 1)
    return lat, lon


@lru_cache(maxsize=1)
def _load_all_metadata() -> Dict[str, dict]:
    """Fetch and parse station_table.txt. Cached for the lifetime of the process."""
    resp = httpx.get(STATION_TABLE_URL, timeout=30)
    resp.raise_for_status()

    stations: Dict[str, dict] = {}
    for line in resp.text.splitlines():
        if line.startswith("#") or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 7:
            continue
        station_id = parts[0].upper()
        name = parts[4] or station_id
        coords = _parse_location(parts[6])
        if coords:
            stations[station_id] = {"lat": coords[0], "lon": coords[1], "name": name}
    return stations


def get_priority_stations() -> Dict[str, dict]:
    """Return metadata for the curated global station list. Skips stations not in table."""
    all_meta = _load_all_metadata()
    return {sid: all_meta[sid] for sid in PRIORITY_IDS if sid in all_meta}
