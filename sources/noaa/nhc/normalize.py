from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from models.event import EarthEvent
from sources.noaa.nhc.config import NHC_SOURCE
from sources.noaa.nhc.schema import CLASSIFICATION_MAP, NHCStorm


def _parse_last_update(last_update: str) -> Optional[datetime]:
    """Parse NHC ISO8601 timestamp string to UTC datetime."""
    try:
        dt = datetime.fromisoformat(last_update)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def normalize_storm(storm: NHCStorm) -> Optional[EarthEvent]:
    """
    Map one NHC active storm to a canonical EarthEvent.
    Returns None if required fields (position, intensity, timestamp) are missing.
    """
    if storm.latitudeNumeric is None or storm.longitudeNumeric is None:
        return None
    if storm.intensity is None or storm.lastUpdate is None:
        return None

    try:
        wind_speed = float(storm.intensity)
    except ValueError:
        return None

    observed_at = _parse_last_update(storm.lastUpdate)
    if observed_at is None:
        return None

    event_type = CLASSIFICATION_MAP.get(storm.classification, "tropical_system")

    # One event per advisory (not per storm), so the storm track is kept as history
    return EarthEvent(
        event_id=f"nhc-{storm.id}-{observed_at.strftime('%Y%m%d%H%M')}",
        event_type=event_type,
        observed_at=observed_at,
        latitude=storm.latitudeNumeric,
        longitude=storm.longitudeNumeric,
        region=storm.name,
        value=wind_speed,
        unit="kt",
        origin=NHC_SOURCE.origin,
        source=NHC_SOURCE.source_id,
        confidence=NHC_SOURCE.confidence,
        ingested_at=datetime.now(tz=timezone.utc),
    )


def normalize_storms(storms: List[NHCStorm]) -> List[EarthEvent]:
    return [e for s in storms if (e := normalize_storm(s)) is not None]
