from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from models.event import EarthEvent
from sources.noaa.weather.config import NWS_SOURCE
from sources.noaa.weather.schema import FIELD_MAP, NWSObservation


def _parse_timestamp(timestamp: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def normalize_observation(
    ba: str,
    station_id: str,
    lat: float,
    lon: float,
    obs: NWSObservation,
) -> List[EarthEvent]:
    """
    Convert one NWS observation into one EarthEvent per measurement type.
    Skips fields where value is None.
    """
    props = obs.properties
    if not props.timestamp:
        return []

    observed_at = _parse_timestamp(props.timestamp)
    if not observed_at:
        return []

    now = datetime.now(tz=timezone.utc)
    ts = observed_at.strftime("%Y%m%d%H%M")
    events: List[EarthEvent] = []

    for field, (event_type, unit) in FIELD_MAP.items():
        qv = getattr(props, field, None)
        if qv is None or qv.value is None:
            continue

        events.append(EarthEvent(
            event_id=f"nws-{ba.lower()}-{station_id.lower()}-{ts}-{field.lower()}",
            event_type=event_type,
            observed_at=observed_at,
            latitude=lat,
            longitude=lon,
            region=ba,
            value=qv.value,
            unit=unit,
            origin=NWS_SOURCE.origin,
            source=NWS_SOURCE.source_id,
            confidence=NWS_SOURCE.confidence,
            ingested_at=now,
        ))

    return events


def normalize_all(
    observations: Dict[str, Tuple[str, List[NWSObservation]]],
    ba_centroids: Dict[str, Tuple[float, float]],
) -> List[EarthEvent]:
    """Normalize every observation for every BA into EarthEvents."""
    all_events: List[EarthEvent] = []
    for ba, (station_id, obs_list) in observations.items():
        lat, lon = ba_centroids[ba]
        for obs in obs_list:
            all_events.extend(normalize_observation(ba, station_id, lat, lon, obs))
    return all_events
