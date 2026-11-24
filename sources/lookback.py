"""
Shared ingestion lookback window.

Each run re-reads the last LOOKBACK of observations so late or skipped
scheduled runs leave no gaps. Re-ingesting the overlap is safe because
event_ids are deterministic and storage MERGEs by event_id.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

LOOKBACK = timedelta(hours=6)


def lookback_cutoff(now: Optional[datetime] = None, lookback: timedelta = LOOKBACK) -> datetime:
    """Earliest observed_at a run should ingest."""
    return (now or datetime.now(tz=timezone.utc)) - lookback
