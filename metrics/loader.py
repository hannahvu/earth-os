"""
Loads events into Polars DataFrames for metric computation.
Reads from BigQuery.
"""
from __future__ import annotations

from typing import List, Optional

import polars as pl
from google.cloud import bigquery

from apps.bigquery.db import FULL_TABLE, build_events_query, get_client
from models.event import EarthEvent


def events_to_df(events: List[EarthEvent]) -> pl.DataFrame:
    """EarthEvents -> DataFrame with the same dtypes BigQuery rows produce (tz-aware datetimes)."""
    if not events:
        return pl.DataFrame()
    return pl.DataFrame([e.model_dump() for e in events])


def load_events_df(
    source: Optional[str] = None,
    event_type: Optional[str] = None,
    origin: Optional[str] = None,
) -> pl.DataFrame:
    """Load events from BigQuery into a Polars DataFrame."""
    sql, params = build_events_query(
        FULL_TABLE,
        {"source": source, "event_type": event_type, "origin": origin},
    )

    client = get_client()
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = list(client.query(sql, job_config=job_config).result())
    if not rows:
        return pl.DataFrame()

    return pl.DataFrame([dict(r) for r in rows])
