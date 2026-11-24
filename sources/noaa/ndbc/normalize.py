from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from models.event import EarthEvent
from sources.lookback import lookback_cutoff
from sources.noaa.ndbc.config import NDBC_SOURCE
from sources.noaa.ndbc.schema import FIELD_MAP, extract_measurements, parse_rows
from sources.noaa.ndbc.stations import get_priority_stations


def _parse_timestamp(row: Dict[str, str]) -> Optional[datetime]:
    """Parse YY MM DD hh mm columns into a UTC datetime."""
    try:
        year = int(row["YY"])
        if year < 100:
            year += 2000
        return datetime(
            year, int(row["MM"]), int(row["DD"]),
            int(row["hh"]), int(row.get("mm", 0)),
            tzinfo=timezone.utc,
        )
    except (KeyError, ValueError):
        return None


def normalize_row(
    station_id: str,
    lat: float,
    lon: float,
    name: str,
    row: Dict[str, str],
    observed_at: datetime,
    ingested_at: datetime,
) -> List[EarthEvent]:
    """One observation row -> one EarthEvent per non-missing measurement."""
    ts = observed_at.strftime("%Y%m%d%H%M")
    events: List[EarthEvent] = []

    for field, value in extract_measurements(row).items():
        event_type, unit = FIELD_MAP[field]
        events.append(EarthEvent(
            event_id=f"ndbc-{station_id.lower()}-{ts}-{field.lower()}",
            event_type=event_type,
            observed_at=observed_at,
            latitude=lat,
            longitude=lon,
            region=name,
            value=value,
            unit=unit,
            origin=NDBC_SOURCE.origin,
            source=NDBC_SOURCE.source_id,
            confidence=NDBC_SOURCE.confidence,
            ingested_at=ingested_at,
        ))

    return events


def normalize_station(
    station_id: str,
    lat: float,
    lon: float,
    name: str,
    text: str,
    cutoff: Optional[datetime] = None,
) -> List[EarthEvent]:
    """
    Convert one station's observations into EarthEvents, one per measurement per row.
    Only rows observed at or after `cutoff` are kept; None keeps every row in the file.
    Skips MM (missing) values and rows with unparseable timestamps.
    """
    now = datetime.now(tz=timezone.utc)
    events: List[EarthEvent] = []

    for row in parse_rows(text):
        observed_at = _parse_timestamp(row)
        if observed_at is None:
            continue
        if cutoff is not None and observed_at < cutoff:
            continue
        events.extend(normalize_row(station_id, lat, lon, name, row, observed_at, now))

    return events


def normalize_all(
    station_texts: Dict[str, str],
    cutoff: Optional[datetime] = None,
) -> List[EarthEvent]:
    """
    Normalize all fetched station texts into EarthEvents.
    `cutoff` defaults to the shared lookback window.
    """
    cutoff = cutoff or lookback_cutoff()
    station_metadata = get_priority_stations()
    all_events: List[EarthEvent] = []

    for station_id, text in station_texts.items():
        meta = station_metadata.get(station_id.upper())
        if not meta:
            continue
        events = normalize_station(
            station_id=station_id,
            lat=meta["lat"],
            lon=meta["lon"],
            name=meta["name"],
            text=text,
            cutoff=cutoff,
        )
        all_events.extend(events)

    return all_events
