from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from models.event import EarthEvent
from sources.usgs.config import USGS_SOURCE
from sources.usgs.schema import USGSFeature

REVIEWED_CONFIDENCE = 0.95
AUTOMATIC_CONFIDENCE = 0.70


def _ms_to_datetime(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def normalize_feature(feature: USGSFeature) -> Optional[EarthEvent]:
    """Map one USGS GeoJSON feature to a canonical EarthEvent. Returns None if mag is missing."""
    props = feature.properties

    if props.mag is None:
        return None

    # coordinates are [longitude, latitude, depth_km] — note order
    lon, lat, _ = feature.geometry.coordinates

    confidence = (
        REVIEWED_CONFIDENCE if props.status == "reviewed" else AUTOMATIC_CONFIDENCE
    )

    return EarthEvent(
        event_id=f"usgs-{feature.id}",
        event_type="earthquake",
        observed_at=_ms_to_datetime(props.time),
        latitude=lat,
        longitude=lon,
        region=props.place or "unknown",
        value=props.mag,
        unit=props.magType or "mw",
        origin=USGS_SOURCE.origin,
        source=USGS_SOURCE.source_id,
        confidence=confidence,
        ingested_at=datetime.now(tz=timezone.utc),
    )


def normalize_features(features: List[USGSFeature]) -> List[EarthEvent]:
    return [e for f in features if (e := normalize_feature(f)) is not None]
