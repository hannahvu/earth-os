"""
Storage layer tests — no API calls, no .env needed.

Run via PyCharm run button or:
    uv run pytest apps/api/storage/test/test_storage.py -s
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.api.storage.db import get_events, init_db, upsert_events
from models.event import EarthEvent


def _make_event(event_id: str, region: str = "ERCO", value: float = 50000.0) -> EarthEvent:
    now = datetime.now(tz=timezone.utc)
    return EarthEvent(
        event_id=event_id,
        event_type="grid_demand",
        observed_at=now,
        latitude=31.5,
        longitude=-99.3,
        region=region,
        value=value,
        unit="megawatthours",
        origin="observed",
        source="EIA",
        confidence=0.99,
        ingested_at=now,
    )


def test_init_db_creates_table(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)
    events = get_events(db)
    assert events == []


def test_upsert_and_query_round_trip(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)

    event = _make_event("eia-erco-2026-08-08t10-d")
    upsert_events([event], db)

    results = get_events(db)
    assert len(results) == 1
    r = results[0]
    assert r.event_id == event.event_id
    assert r.region == "ERCO"
    assert r.value == 50000.0
    assert r.origin == "observed"
    assert r.observed_at.tzinfo is not None


def test_upsert_is_idempotent(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)

    event = _make_event("eia-erco-2026-08-08t10-d")
    upsert_events([event], db)
    upsert_events([event], db)

    results = get_events(db)
    assert len(results) == 1


def test_upsert_updates_value_on_conflict(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)

    original = _make_event("eia-erco-2026-08-08t10-d", value=50000.0)
    upsert_events([original], db)

    revised = _make_event("eia-erco-2026-08-08t10-d", value=51234.0)
    upsert_events([revised], db)

    results = get_events(db)
    assert len(results) == 1
    assert results[0].value == 51234.0


def test_get_events_filter_by_region(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)

    upsert_events([
        _make_event("eia-erco-2026-08-08t10-d", region="ERCO"),
        _make_event("eia-ciso-2026-08-08t10-d", region="CISO"),
        _make_event("eia-pjm-2026-08-08t10-d",  region="PJM"),
    ], db)

    results = get_events(db, region="CISO")
    assert len(results) == 1
    assert results[0].region == "CISO"


def test_get_events_filter_by_source(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)

    eia = _make_event("eia-erco-2026-08-08t10-d", region="ERCO")
    usgs = _make_event("usgs-abc123", region="California")
    usgs = usgs.model_copy(update={"source": "USGS", "event_type": "earthquake"})
    upsert_events([eia, usgs], db)

    results = get_events(db, source="USGS")
    assert len(results) == 1
    assert results[0].source == "USGS"

    results = get_events(db, source="EIA")
    assert len(results) == 1
    assert results[0].source == "EIA"


def test_get_events_respects_limit(tmp_path):
    db = str(tmp_path / "test.db")
    init_db(db)

    events = [_make_event(f"eia-erco-2026-08-08t{h:02d}-d") for h in range(10)]
    upsert_events(events, db)

    results = get_events(db, limit=3)
    assert len(results) == 3
