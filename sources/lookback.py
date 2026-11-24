"""
Shared ingestion lookback window.

Each run re-reads from shortly before the newest data already stored
(the BigQuery watermark), so a late, skipped or failed run is filled by
the next one. Re-ingesting the overlap is safe because event_ids are
deterministic and storage MERGEs by event_id.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

LOOKBACK = timedelta(hours=6)       # always re-read at least this much (late-arriving rows)
MAX_LOOKBACK = timedelta(days=7)    # NWS keeps ~7 days of observations; NDBC ~45
OVERLAP = timedelta(hours=1)        # re-read this far before the watermark


def lookback_cutoff(now: Optional[datetime] = None, lookback: timedelta = LOOKBACK) -> datetime:
    """Earliest observed_at a run should ingest, ignoring stored data."""
    return (now or datetime.now(tz=timezone.utc)) - lookback


def cutoff_from_watermark(
    watermark: Optional[datetime],
    now: Optional[datetime] = None,
    min_lookback: timedelta = LOOKBACK,
    max_lookback: timedelta = MAX_LOOKBACK,
    overlap: timedelta = OVERLAP,
) -> datetime:
    """
    Earliest observed_at to ingest, given the newest stored observed_at.
    Reaches back to the watermark (minus overlap) to fill gaps, but always
    at least min_lookback and never more than max_lookback. No watermark
    (a new source) starts at max_lookback.
    """
    now = now or datetime.now(tz=timezone.utc)
    floor = now - max_lookback
    if watermark is None:
        return floor
    return max(floor, min(watermark - overlap, now - min_lookback))
