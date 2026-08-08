"""
FastAPI endpoint tests — no live API calls, uses a temp SQLite DB.

Run via PyCharm run button or:
    uv run pytest apps/api/test/test_api.py -v
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.storage.db import init_db, upsert_events
from models.event import EarthEvent

client = TestClient(app)


def _make_event(event_id: str, region: str, value: float = 50000.0) -> EarthEvent:
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


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Temp DB pre-loaded with 3 events across 2 regions."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("EARTHOS_DB", db_path)
    init_db(db_path)
    upsert_events([
        _make_event("eia-erco-2026-08-08t10-d", region="ERCO", value=80000.0),
        _make_event("eia-erco-2026-08-08t11-d", region="ERCO", value=82000.0),
        _make_event("eia-ciso-2026-08-08t10-d", region="CISO", value=35000.0),
    ], db_path)
    return db_path


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_events_returns_all(db):
    resp = client.get("/events")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 3


def test_list_events_filter_by_region(db):
    resp = client.get("/events?region=ERCO")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 2
    assert all(e["region"] == "ERCO" for e in events)


def test_list_events_filter_no_match(db):
    resp = client.get("/events?region=PJM")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_events_limit(db):
    resp = client.get("/events?limit=1")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_event_shape(db):
    resp = client.get("/events?region=CISO")
    event = resp.json()[0]
    assert event["event_id"] == "eia-ciso-2026-08-08t10-d"
    assert event["event_type"] == "grid_demand"
    assert event["origin"] == "observed"
    assert event["source"] == "EIA"
    assert event["value"] == 35000.0
    assert event["unit"] == "megawatthours"
    assert "observed_at" in event
    assert "latitude" in event
    assert "longitude" in event
