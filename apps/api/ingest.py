"""
Ingest script — fetch hourly demand for all 5 BAs, normalize, write to SQLite.

Run:
    uv run python apps/api/ingest.py
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from apps.api.storage.db import init_db, upsert_events
from sources.eia.client import fetch_demand
from sources.eia.normalize import normalize_rows

load_dotenv()

RESPONDENTS = ["ERCO", "CISO", "PJM", "MISO", "ISNE"]
DEFAULT_DB = os.environ.get("EARTHOS_DB", "earthos.db")


def ingest_all(db_path: str = DEFAULT_DB, length: int = 100) -> int:
    """Fetch, normalize, and store demand events for all BAs. Returns total event count."""
    init_db(db_path)
    total = 0
    for ba in RESPONDENTS:
        rows = fetch_demand(ba, length=length)
        events = normalize_rows(rows)
        count = upsert_events(events, db_path)
        print(f"  {ba}: {count} events upserted")
        total += count
    print(f"  total: {total} events in {db_path}")
    return total


if __name__ == "__main__":
    ingest_all()
