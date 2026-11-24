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
from sources.noaa.ndbc.client import fetch_all_priority_stations
from sources.noaa.ndbc.normalize import normalize_all as normalize_ndbc
from sources.noaa.nhc.client import fetch_active_storms
from sources.noaa.nhc.normalize import normalize_storms as normalize_nhc
from sources.noaa.weather.client import BA_CENTROIDS, fetch_all_ba_observations
from sources.noaa.weather.normalize import normalize_all as normalize_nws
from metrics.demand_anomaly import compute_demand_anomaly
from metrics.heat_stress import compute_heat_stress
from metrics.seismic_proximity import compute_seismic_proximity
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


def ingest_ndbc(db_path: str) -> int:
    station_texts = fetch_all_priority_stations()
    events = normalize_ndbc(station_texts)
    count = upsert_events(events, db_path)
    print(f"  NDBC buoys: {count} events upserted ({len(station_texts)} stations)")
    return count


def ingest_nhc(db_path: str) -> int:
    storms = fetch_active_storms()
    events = normalize_nhc(storms)
    count = upsert_events(events, db_path)
    print(f"  NHC hurricanes: {count} events upserted ({len(storms)} active storms)")
    return count


def ingest_nws(db_path: str) -> int:
    observations = fetch_all_ba_observations()
    events = normalize_nws(observations, BA_CENTROIDS)
    count = upsert_events(events, db_path)
    print(f"  NWS weather: {count} events upserted ({len(observations)} stations)")
    return count


def ingest_metrics(db_path: str) -> int:
    """Compute derived metrics from ingested source data and upsert results."""
    total = 0
    for label, fn in [
        ("seismic proximity", compute_seismic_proximity),
        ("demand anomaly",    compute_demand_anomaly),
        ("heat stress",       compute_heat_stress),
    ]:
        events = fn(db_path)
        count = upsert_events(events, db_path)
        print(f"  {label}: {count} derived events upserted")
        total += count
    return total


def ingest_all(db_path: str = DEFAULT_DB) -> int:
    """Fetch all sources, compute metrics, and upsert to SQLite. Returns total event count."""
    init_db(db_path)
    total = 0
    total += ingest_eia(db_path)
    total += ingest_usgs(db_path)
    total += ingest_ndbc(db_path)
    total += ingest_nhc(db_path)
    total += ingest_nws(db_path)
    total += ingest_metrics(db_path)
    print(f"  total: {total} events in {db_path}")
    return total


if __name__ == "__main__":
    ingest_all()
