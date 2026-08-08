"""
Ingest script — fetch all sources, normalize, write to SQLite.

Run:
    uv run python apps/api/ingest.py
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from apps.api.storage.db import init_db, upsert_events
from sources.eia.client import fetch_demand
from sources.eia.normalize import normalize_rows as normalize_eia
from sources.usgs.client import fetch_earthquakes
from sources.usgs.normalize import normalize_features as normalize_usgs

load_dotenv()

EIA_RESPONDENTS = ["ERCO", "CISO", "PJM", "MISO", "ISNE"]
DEFAULT_DB = os.environ.get("EARTHOS_DB", "earthos.db")


def ingest_eia(db_path: str, length: int = 100) -> int:
    total = 0
    for ba in EIA_RESPONDENTS:
        rows = fetch_demand(ba, length=length)
        events = normalize_eia(rows)
        count = upsert_events(events, db_path)
        print(f"  EIA {ba}: {count} events upserted")
        total += count
    return total


def ingest_usgs(db_path: str, min_magnitude: float = 2.5, limit: int = 1000) -> int:
    features = fetch_earthquakes(min_magnitude=min_magnitude, limit=limit)
    events = normalize_usgs(features)
    count = upsert_events(events, db_path)
    print(f"  USGS earthquakes: {count} events upserted")
    return count


def ingest_all(db_path: str = DEFAULT_DB) -> int:
    """Fetch all sources, normalize, and upsert to SQLite. Returns total event count."""
    init_db(db_path)
    total = 0
    total += ingest_eia(db_path)
    total += ingest_usgs(db_path)
    print(f"  total: {total} events in {db_path}")
    return total


if __name__ == "__main__":
    ingest_all()
