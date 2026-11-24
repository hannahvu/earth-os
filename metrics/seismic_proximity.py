"""
Seismic proximity metric.

For each M5+ earthquake, checks if it falls within THRESHOLD_KM of a BA centroid.
If so, produces a derived EarthEvent on that BA flagging the proximity.

origin = "derived", source = "EarthOS"
value  = earthquake magnitude (so you know how significant the nearby quake was)
unit   = magnitude type from the source event
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List

import polars as pl

from metrics.loader import load_events_df  # noqa: E402
from models.event import EarthEvent

THRESHOLD_KM = 500.0
MIN_MAGNITUDE = 5.0

BA_CENTROIDS = {
    "ERCO": (31.5, -99.3),
    "CISO": (37.0, -120.0),
    "PJM":  (40.0, -77.0),
    "MISO": (44.0, -90.0),
    "ISNE": (43.0, -71.5),
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _parse_ts(ts_val) -> datetime:
    if isinstance(ts_val, datetime):
        return ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(ts_val)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_seismic_proximity() -> List[EarthEvent]:
    """Load USGS earthquakes from BigQuery and compute proximity alerts."""
    return seismic_proximity_from_df(load_events_df(source="USGS", event_type="earthquake"))


def seismic_proximity_from_df(quakes: pl.DataFrame) -> List[EarthEvent]:
    """
    Returns one derived EarthEvent per (M5+ earthquake, BA centroid within THRESHOLD_KM) pair.
    """
    if quakes.is_empty():
        return []

    quakes = quakes.filter(pl.col("value") >= MIN_MAGNITUDE)
    if quakes.is_empty():
        return []

    now = datetime.now(tz=timezone.utc)
    events: List[EarthEvent] = []

    for row in quakes.iter_rows(named=True):
        q_lat, q_lon = row["latitude"], row["longitude"]

        for ba, (ba_lat, ba_lon) in BA_CENTROIDS.items():
            dist_km = _haversine_km(q_lat, q_lon, ba_lat, ba_lon)
            if dist_km > THRESHOLD_KM:
                continue

            observed_at = _parse_ts(row["observed_at"])
            ts = observed_at.strftime("%Y%m%d%H%M")
            source_id = row["event_id"].replace("usgs-", "")

            events.append(EarthEvent(
                event_id=f"derived-seismic-proximity-{ba.lower()}-{source_id}",
                event_type="seismic_proximity_alert",
                observed_at=observed_at,
                latitude=ba_lat,
                longitude=ba_lon,
                region=ba,
                value=round(row["value"], 2),  # earthquake magnitude
                unit=row["unit"],
                origin="derived",
                source="EarthOS",
                confidence=0.90,
                ingested_at=now,
            ))

    return events
