"""
EarthOS Prefect flows — one flow per source, plus a metrics flow.

Schedules:
  EIA:     hourly         (data publishes ~1hr behind real-time)
  USGS:    every 10 min   (automatic detections arrive fast)
  NDBC:    every 10 min   (buoys report on ~10min interval)
  NWS:     hourly
  NHC:     every 3 hrs    (advisory cycle)
  Metrics: hourly, after sources complete
"""
from __future__ import annotations

from datetime import datetime, timezone

from prefect import flow, task, get_run_logger
from prefect.schedules import Cron

from apps.bigquery.db import init_table, upsert_events
from metrics.demand_anomaly import compute_demand_anomaly
from metrics.heat_stress import compute_heat_stress
from metrics.seismic_proximity import compute_seismic_proximity
from sources.eia.client import fetch_demand
from sources.eia.normalize import normalize_rows as normalize_eia
from sources.noaa.ndbc.client import fetch_all_priority_stations
from sources.noaa.ndbc.normalize import normalize_all as normalize_ndbc
from sources.noaa.nhc.client import fetch_active_storms
from sources.noaa.nhc.normalize import normalize_storms as normalize_nhc
from sources.noaa.weather.client import BA_CENTROIDS, fetch_all_ba_observations
from sources.noaa.weather.normalize import normalize_all as normalize_nws
from sources.usgs.client import fetch_earthquakes
from sources.usgs.normalize import normalize_features as normalize_usgs

EIA_RESPONDENTS = ["ERCO", "CISO", "PJM", "MISO", "ISNE"]

# ── Tasks ────────────────────────────────────────────────────────────────────

@task(retries=3, retry_delay_seconds=30, name="ingest-eia-ba")
def ingest_eia_ba(ba: str, length: int = 100) -> int:
    logger = get_run_logger()
    rows = fetch_demand(ba, length=length)
    events = normalize_eia(rows)
    count = upsert_events(events)
    logger.info(f"EIA {ba}: {count} events upserted")
    return count


@task(retries=3, retry_delay_seconds=30, name="ingest-usgs")
def ingest_usgs_task(min_magnitude: float = 2.5, limit: int = 1000) -> int:
    logger = get_run_logger()
    features = fetch_earthquakes(min_magnitude=min_magnitude, limit=limit)
    events = normalize_usgs(features)
    count = upsert_events(events)
    logger.info(f"USGS: {count} events upserted")
    return count


@task(retries=3, retry_delay_seconds=30, name="ingest-ndbc")
def ingest_ndbc_task() -> int:
    logger = get_run_logger()
    station_texts = fetch_all_priority_stations()
    events = normalize_ndbc(station_texts)
    count = upsert_events(events)
    logger.info(f"NDBC: {count} events upserted ({len(station_texts)} stations)")
    return count


@task(retries=2, retry_delay_seconds=60, name="ingest-nhc")
def ingest_nhc_task() -> int:
    logger = get_run_logger()
    storms = fetch_active_storms()
    events = normalize_nhc(storms)
    count = upsert_events(events)
    logger.info(f"NHC: {count} events upserted ({len(storms)} active storms)")
    return count


@task(retries=3, retry_delay_seconds=30, name="ingest-nws")
def ingest_nws_task() -> int:
    logger = get_run_logger()
    observations = fetch_all_ba_observations()
    events = normalize_nws(observations, BA_CENTROIDS)
    count = upsert_events(events)
    logger.info(f"NWS: {count} events upserted ({len(observations)} BAs)")
    return count


@task(retries=2, retry_delay_seconds=60, name="compute-metrics")
def compute_metrics_task() -> int:
    logger = get_run_logger()
    total = 0
    for label, fn in [
        ("seismic_proximity", compute_seismic_proximity),
        ("demand_anomaly",    compute_demand_anomaly),
        ("heat_stress",       compute_heat_stress),
    ]:
        events = fn()
        count = upsert_events(events)
        logger.info(f"{label}: {count} derived events")
        total += count
    return total


# ── Flows ────────────────────────────────────────────────────────────────────

@flow(name="earthos-eia", log_prints=True)
def eia_flow():
    init_table()
    for ba in EIA_RESPONDENTS:
        ingest_eia_ba(ba)


@flow(name="earthos-usgs", log_prints=True)
def usgs_flow():
    init_table()
    ingest_usgs_task()


@flow(name="earthos-ndbc", log_prints=True)
def ndbc_flow():
    init_table()
    ingest_ndbc_task()


@flow(name="earthos-nhc", log_prints=True)
def nhc_flow():
    init_table()
    ingest_nhc_task()


@flow(name="earthos-nws", log_prints=True)
def nws_flow():
    init_table()
    ingest_nws_task()


@flow(name="earthos-metrics", log_prints=True)
def metrics_flow():
    """Derived metrics — runs after source flows complete."""
    compute_metrics_task()


@flow(name="earthos-all", log_prints=True)
def all_sources_flow():
    """Run all sources sequentially then compute metrics. For manual full runs."""
    init_table()
    for ba in EIA_RESPONDENTS:
        ingest_eia_ba(ba)
    ingest_usgs_task()
    ingest_ndbc_task()
    ingest_nhc_task()
    ingest_nws_task()
    compute_metrics_task()


if __name__ == "__main__":
    all_sources_flow()
