"""
EIA adapter tests — run via PyCharm run button or:
    uv run pytest sources/eia/test/test_eia.py -s
"""
import json
import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()

needs_key = pytest.mark.skipif("EIA_API_KEY" not in os.environ, reason="EIA_API_KEY not set")

RESPONDENTS = ["ERCO", "CISO", "PJM", "MISO", "ISNE"]


# ---------------------------------------------------------------------------
# Step 2 (exploration) — kept for reference, shows raw API shape
# ---------------------------------------------------------------------------

@needs_key
def test_raw_response_shape():
    """Confirm the raw API response shape and print for inspection."""
    from sources.eia.schema import EIARawResponse

    BASE_URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
    params = {
        "api_key": os.environ["EIA_API_KEY"],
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": "ERCO",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5,
    }
    resp = httpx.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    raw = resp.json()

    print("\n=== Row keys ===", list(raw["response"]["data"][0].keys()))
    print("=== Type values seen ===", {r["type"] for r in raw["response"]["data"]})

    parsed = EIARawResponse.model_validate(raw)
    assert len(parsed.response.data) > 0
    row = parsed.response.data[0]
    assert row.respondent == "ERCO"
    assert row.value.isdigit() or row.value.replace(".", "").isdigit()


# ---------------------------------------------------------------------------
# Step 4 — client
# ---------------------------------------------------------------------------

@needs_key
def test_client_returns_demand_rows_only():
    """Client must filter to type=D and return typed EIARow objects."""
    from sources.eia.client import fetch_demand

    rows = fetch_demand("ERCO", length=10)

    print(f"\n=== Fetched {len(rows)} demand rows for ERCO ===")
    for r in rows[:3]:
        print(f"  {r.period}  {r.respondent}  type={r.type}  value={r.value} {r.value_units}")

    assert len(rows) > 0
    assert all(r.type == "D" for r in rows), "client must filter to demand rows only"


@needs_key
def test_client_all_bas():
    """Client can fetch at least one demand row for each target BA."""
    from sources.eia.client import fetch_demand

    for ba in RESPONDENTS:
        rows = fetch_demand(ba, length=5)
        print(f"  {ba}: {len(rows)} rows")
        assert len(rows) > 0, f"no demand rows returned for {ba}"


# ---------------------------------------------------------------------------
# Step 5 — normalize
# ---------------------------------------------------------------------------

@needs_key
def test_normalize_produces_earth_events():
    """Full pipeline: fetch -> normalize -> EarthEvent with correct fields."""
    from sources.eia.client import fetch_demand
    from sources.eia.normalize import normalize_rows
    from models.event import EarthEvent

    rows = fetch_demand("ERCO", length=10)
    events = normalize_rows(rows)

    print(f"\n=== {len(events)} EarthEvents from ERCO ===")
    for e in events[:3]:
        print(json.dumps(e.model_dump(mode="json"), indent=2))

    assert len(events) > 0
    e = events[0]
    assert isinstance(e, EarthEvent)
    assert e.event_type == "grid_demand"
    assert e.origin == "observed"
    assert e.source == "EIA"
    assert e.region == "ERCO"
    assert e.latitude != 0.0 and e.longitude != 0.0
    assert e.value > 0
    assert e.observed_at.tzinfo is not None


@needs_key
def test_normalize_skips_non_demand_rows():
    """normalize_row must return None for type != D."""
    from sources.eia.normalize import normalize_row
    from sources.eia.schema import EIARow

    forecast_row = EIARow(**{
        "period": "2026-08-09T05",
        "respondent": "ERCO",
        "respondent-name": "Electric Reliability Council of Texas, Inc.",
        "type": "DF",
        "type-name": "Day-ahead demand forecast",
        "value": "67282",
        "value-units": "megawatthours",
    })
    assert normalize_row(forecast_row) is None
