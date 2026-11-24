from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, List, Optional

from models.event import EarthEvent

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    latitude    REAL NOT NULL,
    longitude   REAL NOT NULL,
    region      TEXT NOT NULL,
    value       REAL NOT NULL,
    unit        TEXT NOT NULL,
    origin      TEXT NOT NULL,
    source      TEXT NOT NULL,
    confidence  REAL NOT NULL,
    ingested_at TEXT NOT NULL
)
"""

_UPSERT = """
INSERT INTO events (
    event_id, event_type, observed_at, latitude, longitude,
    region, value, unit, origin, source, confidence, ingested_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(event_id) DO UPDATE SET
    value       = excluded.value,
    ingested_at = excluded.ingested_at
"""


@contextmanager
def _connect(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _to_params(event: EarthEvent) -> tuple:
    return (
        event.event_id,
        event.event_type,
        event.observed_at.isoformat(),
        event.latitude,
        event.longitude,
        event.region,
        event.value,
        event.unit,
        event.origin,
        event.source,
        event.confidence,
        event.ingested_at.isoformat(),
    )


def _from_row(row: sqlite3.Row) -> EarthEvent:
    return EarthEvent(
        event_id=row["event_id"],
        event_type=row["event_type"],
        observed_at=datetime.fromisoformat(row["observed_at"]),
        latitude=row["latitude"],
        longitude=row["longitude"],
        region=row["region"],
        value=row["value"],
        unit=row["unit"],
        origin=row["origin"],
        source=row["source"],
        confidence=row["confidence"],
        ingested_at=datetime.fromisoformat(row["ingested_at"]),
    )


def init_db(db_path: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(_CREATE_TABLE)


def upsert_events(events: List[EarthEvent], db_path: str) -> int:
    """Insert or update events by event_id. Returns number of rows processed."""
    with _connect(db_path) as conn:
        conn.executemany(_UPSERT, [_to_params(e) for e in events])
    return len(events)


def get_events(
    db_path: str,
    region: Optional[str] = None,
    event_type: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 500,
) -> List[EarthEvent]:
    """Query events, optionally filtered by region, event_type, and/or source, ordered by observed_at desc."""
    filters = []
    params: list = []

    if region:
        filters.append("region = ?")
        params.append(region)
    if event_type:
        filters.append("event_type = ?")
        params.append(event_type)
    if source:
        filters.append("source = ?")
        params.append(source)

    query = "SELECT * FROM events"
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY observed_at DESC LIMIT ?"
    params.append(limit)

    with _connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_from_row(r) for r in rows]
