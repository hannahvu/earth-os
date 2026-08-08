from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from models.event import EarthEvent
from sources.eia.config import EIA_SOURCE
from sources.eia.schema import EIARow

# Approximate centroids of each balancing authority's service territory
BA_CENTROIDS: dict[str, tuple[float, float]] = {
    "ERCO": (31.5, -99.3),   # ERCOT — central Texas
    "CISO": (37.0, -120.0),  # CAISO — central California
    "PJM":  (40.0, -77.0),   # PJM — mid-Atlantic
    "MISO": (44.0, -90.0),   # MISO — midwest
    "ISNE": (43.0, -71.5),   # ISO-NE — New England
}


def parse_period(period: str) -> datetime:
    # API format: "2026-08-09T05" (YYYY-MM-DDTHH, always UTC)
    return datetime.strptime(period, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)


def normalize_row(row: EIARow) -> Optional[EarthEvent]:
    """Map one raw EIA row to a canonical EarthEvent. Returns None for non-demand rows."""
    if row.type != "D":
        return None

    centroid = BA_CENTROIDS.get(row.respondent)
    if centroid is None:
        return None

    lat, lon = centroid
    return EarthEvent(
        event_id=f"eia-{row.respondent}-{row.period}-{row.type}".lower(),
        event_type="grid_demand",
        observed_at=parse_period(row.period),
        latitude=lat,
        longitude=lon,
        region=row.respondent,
        value=float(row.value),
        unit=row.value_units,
        origin=EIA_SOURCE.origin,
        source=EIA_SOURCE.source_id,
        confidence=EIA_SOURCE.confidence,
        ingested_at=datetime.now(tz=timezone.utc),
    )


def normalize_rows(rows: list[EIARow]) -> list[EarthEvent]:
    return [e for row in rows if (e := normalize_row(row)) is not None]
