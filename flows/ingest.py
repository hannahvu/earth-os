"""
EarthOS hourly ingest — plain Python, scheduled by GitHub Actions
(.github/workflows/ingest.yml).

    uv run python -m flows.ingest

1. Fetch + normalize every source (each re-reads the shared lookback window)
2. One BigQuery MERGE for all source events
3. Compute derived metrics from BigQuery
4. One BigQuery MERGE for all metric events

A failing source or metric is logged and reported; the rest still land.
Exits 1 if anything failed, so the Actions run shows red.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from functools import partial
from typing import Callable, Dict, List

from apps.bigquery.db import init_table, upsert_events
from metrics.demand_anomaly import compute_demand_anomaly
from metrics.heat_stress import compute_heat_stress
from metrics.seismic_proximity import compute_seismic_proximity
from models.event import EarthEvent
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

log = logging.getLogger("earthos.ingest")

Fetcher = Callable[[], List[EarthEvent]]

EIA_RESPONDENTS = ["ERCO", "CISO", "PJM", "MISO", "ISNE"]


# ── Sources: fetch + normalize, no writes ────────────────────────────────────

def fetch_eia_ba(ba: str) -> List[EarthEvent]:
    return normalize_eia(fetch_demand(ba, length=100))


def fetch_usgs() -> List[EarthEvent]:
    return normalize_usgs(fetch_earthquakes(min_magnitude=2.5, limit=1000))


def fetch_ndbc() -> List[EarthEvent]:
    return normalize_ndbc(fetch_all_priority_stations())


def fetch_nhc() -> List[EarthEvent]:
    return normalize_nhc(fetch_active_storms())


def fetch_nws() -> List[EarthEvent]:
    return normalize_nws(fetch_all_ba_observations(), BA_CENTROIDS)


# One entry per BA for EIA, so one BA's outage doesn't drop the other four
SOURCES: Dict[str, Fetcher] = {
    **{f"EIA-{ba}": partial(fetch_eia_ba, ba) for ba in EIA_RESPONDENTS},
    "USGS": fetch_usgs,
    "NDBC": fetch_ndbc,
    "NHC":  fetch_nhc,
    "NWS":  fetch_nws,
}

METRICS: Dict[str, Fetcher] = {
    "seismic_proximity": compute_seismic_proximity,
    "demand_anomaly":    compute_demand_anomaly,
    "heat_stress":       compute_heat_stress,
}


# ── Runner ───────────────────────────────────────────────────────────────────

@dataclass
class RunResult:
    counts: Dict[str, int] = field(default_factory=dict)
    failed: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


def collect(fetchers: Dict[str, Fetcher], result: RunResult) -> List[EarthEvent]:
    """Call every fetcher; log and record failures instead of raising."""
    events: List[EarthEvent] = []
    for name, fetch in fetchers.items():
        try:
            batch = fetch()
        except Exception:
            log.exception("%s failed", name)
            result.failed.append(name)
            continue
        result.counts[name] = len(batch)
        log.info("%s: %d events", name, len(batch))
        events.extend(batch)
    return events


def run_hourly(
    sources: Dict[str, Fetcher] = SOURCES,
    metrics: Dict[str, Fetcher] = METRICS,
    upsert: Callable[[List[EarthEvent]], int] = upsert_events,
    init: Callable[[], None] = init_table,
) -> RunResult:
    """
    Sources -> one upsert -> metrics -> one upsert.
    Metrics run after the source upsert because they read from BigQuery.
    Upsert errors propagate: if the write fails, the run has failed.
    """
    result = RunResult()
    init()

    source_events = collect(sources, result)
    if source_events:
        upsert(source_events)

    metric_events = collect(metrics, result)
    if metric_events:
        upsert(metric_events)

    return result


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs every request URL at INFO, and EIA's URL carries api_key.
    # Actions logs are public on this repo, so keep request URLs out of them.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = run_hourly()
    total = sum(result.counts.values())
    if result.ok:
        log.info("done: %d events, all sources and metrics succeeded", total)
        return 0
    log.error("done: %d events, FAILED: %s", total, ", ".join(result.failed))
    return 1


if __name__ == "__main__":
    sys.exit(main())
