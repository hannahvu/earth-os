"""
EarthOS hourly ingest — plain Python, scheduled by GitHub Actions
(.github/workflows/ingest.yml).

    uv run python -m flows.ingest

1. Read BigQuery watermarks (newest stored observed_at per source)
2. Fetch + normalize every source from its cutoff (fills any gap since the
   last successful run, up to 7 days back)
3. One BigQuery MERGE for all source events
4. Compute derived metrics from BigQuery
5. One BigQuery MERGE for all metric events

A failing source or metric is logged and reported; the rest still land.
Exits 1 if anything failed, so the Actions run shows red.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Callable, Dict, List, Optional, Tuple

from apps.bigquery.db import Watermarks, get_watermarks, init_table, upsert_events
from metrics.demand_anomaly import compute_demand_anomaly
from metrics.heat_stress import compute_heat_stress
from metrics.seismic_proximity import compute_seismic_proximity
from models.event import EarthEvent
from sources.eia.client import fetch_demand
from sources.eia.normalize import normalize_rows as normalize_eia
from sources.lookback import LOOKBACK, MAX_LOOKBACK, cutoff_from_watermark
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
EIA_MIN_LOOKBACK = timedelta(hours=100)  # EIA-930 revises recent hours for a few days
EIA_MAX_ROWS = 5000                      # API page limit; 7 days is 168 rows


@dataclass(frozen=True)
class Source:
    fetch: Callable[[datetime], List[EarthEvent]]  # fetch + normalize from cutoff, no writes
    key: Tuple[str, Optional[str]]                  # watermark key: (source, region or None)
    min_lookback: timedelta = LOOKBACK


# ── Sources: fetch + normalize, no writes ────────────────────────────────────

def eia_start(cutoff: datetime) -> str:
    """EIA period format: YYYY-MM-DDTHH, UTC."""
    return cutoff.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def fetch_eia_ba(ba: str, cutoff: datetime) -> List[EarthEvent]:
    return normalize_eia(fetch_demand(ba, length=EIA_MAX_ROWS, start=eia_start(cutoff)))


def fetch_usgs(cutoff: datetime) -> List[EarthEvent]:
    # Ignores cutoff: the latest 1000 M2.5+ events span weeks, which also
    # re-reads events USGS revises (automatic -> reviewed) days later
    return normalize_usgs(fetch_earthquakes(min_magnitude=2.5, limit=1000))


def fetch_ndbc(cutoff: datetime) -> List[EarthEvent]:
    return normalize_ndbc(fetch_all_priority_stations(), cutoff=cutoff)


def fetch_nhc(cutoff: datetime) -> List[EarthEvent]:
    # Ignores cutoff: the feed only has current storms
    return normalize_nhc(fetch_active_storms())


def fetch_nws(cutoff: datetime) -> List[EarthEvent]:
    return normalize_nws(fetch_all_ba_observations(start=cutoff), BA_CENTROIDS)


# One entry per BA for EIA, so one BA's outage doesn't drop the other four
SOURCES: Dict[str, Source] = {
    **{
        f"EIA-{ba}": Source(partial(fetch_eia_ba, ba), key=("EIA", ba), min_lookback=EIA_MIN_LOOKBACK)
        for ba in EIA_RESPONDENTS
    },
    "USGS": Source(fetch_usgs, key=("USGS", None)),
    "NDBC": Source(fetch_ndbc, key=("NDBC", None)),
    "NHC":  Source(fetch_nhc,  key=("NHC", None)),
    "NWS":  Source(fetch_nws,  key=("NWS", None)),
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


def source_cutoffs(
    sources: Dict[str, Source],
    marks: Watermarks,
    now: datetime,
) -> Dict[str, datetime]:
    """Per-source cutoff from its watermark (see sources.lookback.cutoff_from_watermark)."""
    return {
        name: cutoff_from_watermark(marks.get(src.key), now=now, min_lookback=src.min_lookback)
        for name, src in sources.items()
    }


def run_hourly(
    sources: Dict[str, Source] = SOURCES,
    metrics: Dict[str, Fetcher] = METRICS,
    upsert: Callable[[List[EarthEvent]], int] = upsert_events,
    init: Callable[[], None] = init_table,
    watermarks: Callable[[datetime], Watermarks] = get_watermarks,
    now: Optional[datetime] = None,
    since: Optional[datetime] = None,
) -> RunResult:
    """
    Watermarks -> sources (from cutoff) -> one upsert -> metrics -> one upsert.
    `since` forces every cutoff at least that far back, to re-fill holes
    that sit before the watermark (e.g. `python -m flows.ingest --since ...`).
    Metrics run after the source upsert because they read from BigQuery.
    Upsert errors propagate: if the write fails, the run has failed.
    """
    now = now or datetime.now(tz=timezone.utc)
    result = RunResult()
    init()

    cutoffs = source_cutoffs(sources, watermarks(now - MAX_LOOKBACK), now)
    if since is not None:
        cutoffs = {name: min(cutoff, since) for name, cutoff in cutoffs.items()}
    for name, cutoff in cutoffs.items():
        log.info("%s: from %s", name, cutoff.strftime("%Y-%m-%d %H:%M UTC"))
    fetchers = {name: partial(src.fetch, cutoffs[name]) for name, src in sources.items()}

    source_events = collect(fetchers, result)
    if source_events:
        upsert(source_events)

    metric_events = collect(metrics, result)
    if metric_events:
        upsert(metric_events)

    return result


def parse_since(value: str) -> datetime:
    """ISO8601 -> aware UTC datetime; a naive value is taken as UTC."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EarthOS hourly ingest")
    parser.add_argument(
        "--since", type=parse_since, default=None,
        help="re-fill from this UTC time, e.g. 2026-11-24T00:00Z (default: from watermarks)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs every request URL at INFO, and EIA's URL carries api_key.
    # Actions logs are public on this repo, so keep request URLs out of them.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = run_hourly(since=args.since)
    total = sum(result.counts.values())
    if result.ok:
        log.info("done: %d events, all sources and metrics succeeded", total)
        return 0
    log.error("done: %d events, FAILED: %s", total, ", ".join(result.failed))
    return 1


if __name__ == "__main__":
    sys.exit(main())
