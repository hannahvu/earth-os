"""
Metrics layer tests.

Metric math is tested on in-memory Polars DataFrames built from fixture
events. No BigQuery or API calls. The loader has one unit test with a
fake client and one live test against BigQuery (skipped without credentials).

Run via PyCharm run button or:
    uv run pytest metrics/test/test_metrics.py -s
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import List

import google.auth
import polars as pl
import pytest

import metrics.loader as loader
from metrics.demand_anomaly import demand_anomaly_from_df
from metrics.heat_stress import heat_stress_from_dfs
from metrics.loader import events_to_df, load_events_df
from metrics.seismic_proximity import _haversine_km, seismic_proximity_from_df
from models.event import EarthEvent


# ---------------------------------------------------------------------------
# Fixtures — in-memory events
# ---------------------------------------------------------------------------

def _make_event(**kwargs) -> EarthEvent:
    defaults = dict(
        event_id="test-id",
        event_type="grid_demand",
        observed_at=datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc),
        latitude=31.5, longitude=-99.3,
        region="ERCO", value=80000.0, unit="megawatthours",
        origin="observed", source="EIA", confidence=0.99,
        ingested_at=datetime.now(tz=timezone.utc),
    )
    defaults.update(kwargs)
    return EarthEvent(**defaults)


def _demand_events() -> List[EarthEvent]:
    """
    7 days of hourly EIA demand for ERCO and CISO.
    7 days gives enough data points per hour-of-day for z-scores to be meaningful.
    """
    events = []
    base = datetime(2026, 8, 6, 0, 0, tzinfo=timezone.utc)
    for ba, lat, lon, base_demand in [("ERCO", 31.5, -99.3, 80000), ("CISO", 37.0, -120.0, 35000)]:
        for h in range(168):
            ts = base + timedelta(hours=h)
            # inject one obvious spike at hour 48 for ERCO (1.8x normal)
            val = base_demand * 1.8 if (ba == "ERCO" and h == 48) else base_demand + (h % 24) * 100
            events.append(_make_event(
                event_id=f"eia-{ba.lower()}-{ts.strftime('%Y%m%d%H%M')}-d",
                event_type="grid_demand", source="EIA",
                observed_at=ts, latitude=lat, longitude=lon,
                region=ba, value=float(val), unit="megawatthours",
            ))
    return events


def _quake_events() -> List[EarthEvent]:
    return [
        # M5.5 near CISO (~200km offshore CA)
        _make_event(
            event_id="usgs-abc123",
            event_type="earthquake", source="USGS",
            observed_at=datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc),
            latitude=36.0, longitude=-122.0,
            region="4km W of test", value=5.5, unit="ml",
            confidence=0.95,
        ),
        # M3.0 far from all BAs (mid-Pacific)
        _make_event(
            event_id="usgs-def456",
            event_type="earthquake", source="USGS",
            observed_at=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc),
            latitude=5.0, longitude=-160.0,
            region="Central Pacific", value=3.0, unit="ml",
            confidence=0.95,
        ),
        # M4.0 right next to CISO — close, but below the M5 threshold
        _make_event(
            event_id="usgs-ghi789",
            event_type="earthquake", source="USGS",
            observed_at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
            latitude=37.1, longitude=-120.1,
            region="near CISO", value=4.0, unit="ml",
            confidence=0.95,
        ),
    ]


def _temp_events() -> List[EarthEvent]:
    return [
        _make_event(
            event_id=f"nws-{ba.lower()}-kxxx-202608081000-temperature",
            event_type="air_temperature", source="NWS",
            observed_at=datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc),
            latitude=lat, longitude=lon,
            region=ba, value=temp, unit="degC",
            confidence=0.95,
        )
        for ba, lat, lon, temp in [("ERCO", 31.5, -99.3, 38.0), ("CISO", 37.0, -120.0, 24.0)]
    ]


@pytest.fixture()
def demand_df() -> pl.DataFrame:
    return events_to_df(_demand_events())


@pytest.fixture()
def quakes_df() -> pl.DataFrame:
    return events_to_df(_quake_events())


@pytest.fixture()
def temp_df() -> pl.DataFrame:
    return events_to_df(_temp_events())


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def test_events_to_df_matches_bigquery_dtypes(demand_df):
    # BigQuery returns tz-aware datetimes; a String here is what caused the
    # 2026-10-17 SchemaError in the metrics run
    assert demand_df.schema["observed_at"] == pl.Datetime("us", "UTC")
    assert len(demand_df) == 336  # 168 ERCO + 168 CISO


def test_events_to_df_empty():
    assert events_to_df([]).is_empty()


class _FakeJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class _FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query(self, sql, job_config=None):
        self.calls.append((sql, job_config))
        return _FakeJob(self.rows)


def test_loader_passes_filters_as_params(monkeypatch):
    rows = [e.model_dump() for e in _quake_events()]
    fake = _FakeClient(rows)
    monkeypatch.setattr(loader, "get_client", lambda: fake)

    df = load_events_df(source="USGS", event_type="earthquake")

    sql, job_config = fake.calls[0]
    assert "source = @source" in sql and "event_type = @event_type" in sql
    assert {(p.name, p.value) for p in job_config.query_parameters} == {
        ("source", "USGS"), ("event_type", "earthquake"),
    }
    assert len(df) == 3


def test_loader_returns_empty_df_for_no_rows(monkeypatch):
    monkeypatch.setattr(loader, "get_client", lambda: _FakeClient([]))
    assert load_events_df(source="USGS").is_empty()


def _has_gcp_credentials() -> bool:
    try:
        google.auth.default()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_gcp_credentials(), reason="no GCP credentials")
def test_loader_live_bigquery_dtypes():
    """Read-only check that real BigQuery rows come back in the shape the metrics expect."""
    df = load_events_df(source="EIA", event_type="grid_demand")
    if df.is_empty():
        pytest.skip("no EIA rows in BigQuery")
    assert isinstance(df.schema["observed_at"], pl.Datetime)
    assert df["source"].unique().to_list() == ["EIA"]


# ---------------------------------------------------------------------------
# Seismic proximity
# ---------------------------------------------------------------------------

def test_haversine_known_distance():
    # London to Paris is ~340km
    dist = _haversine_km(51.5, -0.1, 48.9, 2.3)
    assert 330 < dist < 360


def test_seismic_proximity_detects_nearby_quake(quakes_df):
    events = seismic_proximity_from_df(quakes_df)

    print(f"\n=== {len(events)} seismic proximity alerts ===")
    for e in events:
        print(f"  {e.region}: M{e.value} {e.unit}  (event_id={e.event_id})")

    assert len(events) >= 1
    regions = {e.region for e in events}
    assert "CISO" in regions   # M5.5 ~200km offshore CA should trigger CISO


def test_seismic_proximity_ignores_distant_quake(quakes_df):
    events = seismic_proximity_from_df(quakes_df)
    # M3.0 mid-Pacific should not trigger any BA
    assert all("def456" not in e.event_id for e in events)


def test_seismic_proximity_ignores_low_magnitude(quakes_df):
    # M4.0 sits ~15km from the CISO centroid but is below the M5 threshold
    events = seismic_proximity_from_df(quakes_df)
    assert all("ghi789" not in e.event_id for e in events)
    assert all(e.value >= 5.0 for e in events)


def test_seismic_proximity_empty_input():
    assert seismic_proximity_from_df(pl.DataFrame()) == []


def test_seismic_proximity_event_fields(quakes_df):
    events = seismic_proximity_from_df(quakes_df)
    e = next(ev for ev in events if ev.region == "CISO")
    assert e.event_type == "seismic_proximity_alert"
    assert e.origin == "derived"
    assert e.source == "EarthOS"
    assert e.event_id == "derived-seismic-proximity-ciso-abc123"
    assert e.observed_at.tzinfo is not None

    print(f"\n=== CISO seismic proximity event ===")
    print(json.dumps(e.model_dump(mode="json"), indent=2))


# ---------------------------------------------------------------------------
# Demand anomaly
# ---------------------------------------------------------------------------

def test_demand_anomaly_detects_spike(demand_df):
    events = demand_anomaly_from_df(demand_df)

    print(f"\n=== {len(events)} demand anomaly events ===")
    for e in events:
        print(f"  {e.region}: z={e.value:.2f}  {e.observed_at}")

    # The injected 80% spike at ERCO hour 48 (2026-08-08 00:00) should be flagged
    spike = [e for e in events if e.region == "ERCO" and e.observed_at == datetime(2026, 8, 8, 0, 0, tzinfo=timezone.utc)]
    assert len(spike) == 1
    assert spike[0].value > 1.5


def test_demand_anomaly_ignores_regular_pattern(demand_df):
    # CISO has a perfectly repeating daily pattern, so std per hour is 0 and nothing is flagged
    events = demand_anomaly_from_df(demand_df)
    assert all(e.region != "CISO" for e in events)


def test_demand_anomaly_empty_input():
    assert demand_anomaly_from_df(pl.DataFrame()) == []


def test_demand_anomaly_event_fields(demand_df):
    e = demand_anomaly_from_df(demand_df)[0]
    assert e.event_type == "demand_anomaly"
    assert e.origin == "derived"
    assert e.source == "EarthOS"
    assert e.unit == "z_score"
    assert e.event_id.startswith("derived-demand-anomaly-")


# ---------------------------------------------------------------------------
# Heat stress
# ---------------------------------------------------------------------------

def test_heat_stress_produces_events(temp_df, demand_df):
    events = heat_stress_from_dfs(temp_df, demand_df)

    print(f"\n=== {len(events)} heat stress events ===")
    for e in events:
        print(f"  {e.region}: heat_stress={e.value:.3f}")

    assert {e.region for e in events} == {"ERCO", "CISO"}


def test_heat_stress_erco_higher_than_ciso(temp_df, demand_df):
    by_region = {e.region: e.value for e in heat_stress_from_dfs(temp_df, demand_df)}
    # ERCO: 38°C, CISO: 24°C — ERCO should have higher stress score
    assert by_region["ERCO"] > by_region["CISO"]


def test_heat_stress_empty_input(demand_df):
    assert heat_stress_from_dfs(pl.DataFrame(), demand_df) == []


def test_heat_stress_event_fields(temp_df, demand_df):
    e = next(ev for ev in heat_stress_from_dfs(temp_df, demand_df) if ev.region == "ERCO")
    assert e.event_type == "heat_stress_index"
    assert e.origin == "derived"
    assert e.source == "EarthOS"
    assert e.unit == "index"
    assert e.event_id.startswith("derived-heat-stress-erco-")
