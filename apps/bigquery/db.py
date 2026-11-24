from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from google.cloud import bigquery

from models.event import EarthEvent

PROJECT = os.environ.get("GCP_PROJECT", "earth-os-511902")
DATASET = os.environ.get("BQ_DATASET", "earthos")
TABLE = "events"
FULL_TABLE = f"{PROJECT}.{DATASET}.{TABLE}"

SCHEMA = [
    bigquery.SchemaField("event_id",    "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("event_type",  "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("observed_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("latitude",    "FLOAT64",   mode="REQUIRED"),
    bigquery.SchemaField("longitude",   "FLOAT64",   mode="REQUIRED"),
    bigquery.SchemaField("region",      "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("value",       "FLOAT64",   mode="REQUIRED"),
    bigquery.SchemaField("unit",        "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("origin",      "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("source",      "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("confidence",  "FLOAT64",   mode="REQUIRED"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
]

KEY_FIELD = "event_id"
UPDATE_FIELDS = [f.name for f in SCHEMA if f.name != KEY_FIELD]

# Columns callers may filter on. Column names are interpolated into SQL,
# so only these are allowed; values always go through query parameters.
FILTER_FIELDS = ("source", "event_type", "region", "origin")

# Slack below the batch's earliest observed_at when pruning partitions in MERGE.
# Covers source revisions that shift an event's time slightly earlier
# (e.g. a USGS origin-time correction), which would otherwise miss the match.
PARTITION_BUFFER = timedelta(days=1)

STAGING_TTL = timedelta(hours=1)


def get_client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT)


def init_table(table: str = FULL_TABLE) -> None:
    """Create the events table if it doesn't exist."""
    client = get_client()
    try:
        client.get_table(table)
    except Exception:
        t = bigquery.Table(table, schema=SCHEMA)
        t.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="observed_at",
        )
        t.clustering_fields = ["source", "event_type", "region"]
        client.create_table(t)
        print(f"Created table {table}")


# ── Pure builders ────────────────────────────────────────────────────────────

def staging_table_name(table: str = FULL_TABLE) -> str:
    """Unique staging table per upsert, so concurrent runs never share one."""
    return f"{table}_staging_{uuid.uuid4().hex[:8]}"


def event_to_row(e: EarthEvent) -> dict:
    """EarthEvent -> JSON-serializable row for a BigQuery load job."""
    row = e.model_dump()
    row["observed_at"] = e.observed_at.isoformat()
    row["ingested_at"] = e.ingested_at.isoformat()
    return row


def partition_cutoff(events: List[EarthEvent]) -> datetime:
    """Earliest observed_at in the batch, minus PARTITION_BUFFER."""
    return min(e.observed_at for e in events) - PARTITION_BUFFER


def build_merge_sql(target: str, staging: str) -> str:
    """
    MERGE staging into target by event_id.
    The observed_at predicate (bound to @min_observed_at) lets BigQuery prune
    partitions older than the batch instead of scanning the whole table.
    """
    updates = ",\n        ".join(f"{f} = S.{f}" for f in UPDATE_FIELDS)
    return f"""
    MERGE `{target}` T
    USING `{staging}` S
    ON T.{KEY_FIELD} = S.{KEY_FIELD}
       AND T.observed_at >= @min_observed_at
    WHEN MATCHED THEN UPDATE SET
        {updates}
    WHEN NOT MATCHED THEN INSERT ROW
    """


def build_filters(
    filters: Dict[str, Optional[str]],
) -> Tuple[str, List[bigquery.ScalarQueryParameter]]:
    """
    Turn {column: value} into a parameterized WHERE clause.
    None values are skipped. Unknown columns raise ValueError.
    """
    clauses: List[str] = []
    params: List[bigquery.ScalarQueryParameter] = []
    for column, value in filters.items():
        if column not in FILTER_FIELDS:
            raise ValueError(f"Unknown filter column: {column!r}")
        if value is None:
            continue
        clauses.append(f"{column} = @{column}")
        params.append(bigquery.ScalarQueryParameter(column, "STRING", value))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def build_events_query(
    table: str,
    filters: Dict[str, Optional[str]],
    limit: Optional[int] = None,
) -> Tuple[str, List[bigquery.ScalarQueryParameter]]:
    """SELECT events newest-first with optional filters and limit."""
    where, params = build_filters(filters)
    limit_sql = f"LIMIT {int(limit)}" if limit is not None else ""
    sql = f"""
        SELECT * FROM `{table}`
        {where}
        ORDER BY observed_at DESC
        {limit_sql}
    """
    return sql, params


# ── I/O ──────────────────────────────────────────────────────────────────────

def upsert_events(events: List[EarthEvent], table: str = FULL_TABLE) -> int:
    """
    Merge events into BigQuery by event_id.
    Loads rows into a per-call staging table, MERGEs into the target, then
    drops the staging table. Returns number of events processed.
    """
    if not events:
        return 0

    client = get_client()
    staging = staging_table_name(table)

    try:
        staging_table = bigquery.Table(staging, schema=SCHEMA)
        # Safety net: BigQuery drops it on its own if this process dies mid-run
        staging_table.expires = datetime.now(tz=timezone.utc) + STAGING_TTL
        client.create_table(staging_table)

        load_config = bigquery.LoadJobConfig(
            schema=SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )
        rows = [event_to_row(e) for e in events]
        client.load_table_from_json(rows, staging, job_config=load_config).result()

        merge_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("min_observed_at", "TIMESTAMP", partition_cutoff(events)),
        ])
        client.query(build_merge_sql(table, staging), job_config=merge_config).result()
    finally:
        client.delete_table(staging, not_found_ok=True)

    return len(events)


def get_events(
    source: Optional[str] = None,
    event_type: Optional[str] = None,
    region: Optional[str] = None,
    origin: Optional[str] = None,
    limit: int = 1500,
    table: str = FULL_TABLE,
) -> List[EarthEvent]:
    """Query events from BigQuery with optional filters."""
    sql, params = build_events_query(
        table,
        {"source": source, "event_type": event_type, "region": region, "origin": origin},
        limit=limit,
    )
    client = get_client()
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = client.query(sql, job_config=job_config).result()
    return [EarthEvent(**dict(r)) for r in rows]
