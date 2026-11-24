"""
BigQuery storage tests.

Unit tests need no network. Live tests write to a throwaway table in the
earthos dataset (deleted afterwards) and are skipped without GCP credentials.

Run via PyCharm run button or:
    uv run pytest apps/bigquery/test/test_bigquery.py -s
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import google.auth
import pytest

from apps.bigquery.db import (
    DATASET,
    PARTITION_BUFFER,
    PROJECT,
    UPDATE_FIELDS,
    build_events_query,
    build_filters,
    build_merge_sql,
    event_to_row,
    get_client,
    get_events,
    init_table,
    partition_cutoff,
    staging_table_name,
    upsert_events,
)
from models.event import EarthEvent

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def _event(event_id: str = "test-1", observed_at: datetime = NOW, **overrides) -> EarthEvent:
    fields = dict(
        event_id=event_id,
        event_type="earthquake",
        observed_at=observed_at,
        latitude=34.0,
        longitude=-118.0,
        region="Test Region",
        value=3.1,
        unit="ml",
        origin="observed",
        source="USGS",
        confidence=0.70,
        ingested_at=NOW,
    )
    fields.update(overrides)
    return EarthEvent(**fields)


# ---------------------------------------------------------------------------
# Unit — pure builders
# ---------------------------------------------------------------------------

def test_staging_table_names_are_unique():
    names = {staging_table_name("p.d.events") for _ in range(100)}
    assert len(names) == 100
    assert all(n.startswith("p.d.events_staging_") for n in names)


def test_merge_sql_prunes_partitions():
    sql = build_merge_sql("p.d.events", "p.d.events_staging_abc")
    assert "T.observed_at >= @min_observed_at" in sql


def test_merge_sql_updates_every_non_key_field():
    sql = build_merge_sql("p.d.events", "p.d.events_staging_abc")
    update_clause = sql.split("UPDATE SET")[1].split("WHEN NOT MATCHED")[0]
    for field in UPDATE_FIELDS:
        assert f"{field} = S.{field}" in update_clause
    assert "event_id = S.event_id" not in update_clause


def test_partition_cutoff_is_earliest_minus_buffer():
    events = [_event("a", NOW), _event("b", NOW - timedelta(days=10)), _event("c", NOW - timedelta(days=2))]
    assert partition_cutoff(events) == NOW - timedelta(days=10) - PARTITION_BUFFER


def test_event_to_row_serializes_timestamps():
    row = event_to_row(_event())
    assert row["observed_at"] == NOW.isoformat()
    assert row["ingested_at"] == NOW.isoformat()
    assert row["event_id"] == "test-1"


def test_filters_skip_none_values():
    where, params = build_filters({"source": "USGS", "region": None})
    assert where == "WHERE source = @source"
    assert [(p.name, p.value) for p in params] == [("source", "USGS")]


def test_filters_empty_when_all_none():
    assert build_filters({"source": None, "event_type": None}) == ("", [])


def test_filter_values_never_reach_sql():
    malicious = "x' OR 1=1 --"
    sql, params = build_events_query("p.d.events", {"source": malicious})
    assert malicious not in sql
    assert params[0].value == malicious


def test_unknown_filter_column_rejected():
    with pytest.raises(ValueError):
        build_filters({"source; DROP TABLE events": "x"})


def test_events_query_limit():
    sql, _ = build_events_query("p.d.events", {}, limit=5)
    assert "LIMIT 5" in sql
    sql, _ = build_events_query("p.d.events", {})
    assert "LIMIT" not in sql


# ---------------------------------------------------------------------------
# Live — throwaway BigQuery table
# ---------------------------------------------------------------------------

def _has_gcp_credentials() -> bool:
    try:
        google.auth.default()
        return True
    except Exception:
        return False


live = pytest.mark.skipif(not _has_gcp_credentials(), reason="no GCP credentials")


@pytest.fixture
def test_table():
    table = f"{PROJECT}.{DATASET}.events_test_{uuid.uuid4().hex[:8]}"
    init_table(table)
    yield table
    get_client().delete_table(table, not_found_ok=True)


def _row_count(table: str) -> int:
    rows = get_client().query(f"SELECT COUNT(*) AS n FROM `{table}`").result()
    return next(iter(rows)).n


@live
def test_upsert_updates_existing_event(test_table):
    upsert_events([_event(confidence=0.70)], table=test_table)
    upsert_events([_event(confidence=0.95, latitude=34.5)], table=test_table)

    results = get_events(table=test_table)
    assert len(results) == 1
    assert results[0].confidence == 0.95
    assert results[0].latitude == 34.5


@live
def test_upsert_matches_when_revision_shifts_time_earlier(test_table):
    """A revised origin time slightly earlier than the stored one must still match."""
    upsert_events([_event(observed_at=NOW)], table=test_table)
    upsert_events([_event(observed_at=NOW - timedelta(seconds=30))], table=test_table)
    assert _row_count(test_table) == 1


@live
def test_concurrent_upserts_both_land(test_table):
    batch_a = [_event(f"a-{i}") for i in range(5)]
    batch_b = [_event(f"b-{i}") for i in range(5)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda b: upsert_events(b, table=test_table), [batch_a, batch_b]))

    assert results == [5, 5]
    assert _row_count(test_table) == 10


@live
def test_get_events_filters_with_params(test_table):
    upsert_events([_event("q-1"), _event("e-1", source="EIA", event_type="grid_demand")], table=test_table)

    assert [e.event_id for e in get_events(source="EIA", table=test_table)] == ["e-1"]
    assert get_events(source="x' OR 1=1 --", table=test_table) == []


@live
def test_staging_tables_cleaned_up(test_table):
    upsert_events([_event()], table=test_table)
    prefix = test_table.split(".")[-1] + "_staging_"
    leftovers = [t.table_id for t in get_client().list_tables(DATASET) if t.table_id.startswith(prefix)]
    assert leftovers == []
