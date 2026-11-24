"""
NHC adapter tests.

NOTE: test_live_* tests only produce events during hurricane season (June-Nov)
when named storms are active. They will pass with 0 events off-season — that's
correct behaviour, not a test failure.

Run via PyCharm run button or:
    uv run pytest sources/noaa/test/test_nhc_adapter.py -s
"""
from __future__ import annotations

import json
from datetime import timezone

import pytest

from sources.noaa.nhc.client import fetch_active_storms
from sources.noaa.nhc.normalize import normalize_storm, normalize_storms
from sources.noaa.nhc.schema import CLASSIFICATION_MAP, NHCCurrentStorms, NHCStorm

# ---------------------------------------------------------------------------
# Synthetic storm for unit tests — no network required
# ---------------------------------------------------------------------------

SAMPLE_STORM = NHCStorm(
    id="al052024",
    name="DEBBY",
    classification="HU",
    intensity="80",
    pressure="979",
    latitude="29.9N",
    longitude="83.6W",
    latitudeNumeric=29.9,
    longitudeNumeric=-83.6,
    movementDir=360,
    movementSpeed=7,
    lastUpdate="2024-08-05T15:00:00-04:00",
)

SAMPLE_TS = NHCStorm(
    id="ep032024",
    name="CARLOTTA",
    classification="TS",
    intensity="45",
    pressure="998",
    latitudeNumeric=15.2,
    longitudeNumeric=-110.5,
    lastUpdate="2024-08-10T09:00:00-04:00",
)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_schema_parses_empty_response():
    data = NHCCurrentStorms.model_validate({"activeStorms": []})
    assert data.activeStorms == []


def test_schema_parses_storm():
    data = NHCCurrentStorms.model_validate({
        "activeStorms": [SAMPLE_STORM.model_dump()]
    })
    assert len(data.activeStorms) == 1
    assert data.activeStorms[0].name == "DEBBY"


def test_classification_map_coverage():
    """All expected classification codes are in the map."""
    for code in ["HU", "TS", "TD", "SS", "SD", "EX", "LO", "DB"]:
        assert code in CLASSIFICATION_MAP


# ---------------------------------------------------------------------------
# Normalize — unit tests against synthetic data
# ---------------------------------------------------------------------------

def test_normalize_hurricane():
    event = normalize_storm(SAMPLE_STORM)
    assert event is not None
    print(f"\n=== Synthetic hurricane event ===")
    print(json.dumps(event.model_dump(mode="json"), indent=2))

    assert event.event_id == "nhc-al052024-202408051900"  # 15:00 -04:00 = 19:00 UTC
    assert event.event_type == "hurricane"
    assert event.region == "DEBBY"
    assert event.value == 80.0
    assert event.unit == "kt"
    assert event.latitude == 29.9
    assert event.longitude == -83.6
    assert event.origin == "observed"
    assert event.source == "NHC"
    assert event.confidence == 0.95
    assert event.observed_at.tzinfo is not None
    assert event.observed_at == event.observed_at.astimezone(timezone.utc)


def test_normalize_tropical_storm():
    event = normalize_storm(SAMPLE_TS)
    assert event is not None
    assert event.event_type == "tropical_storm"
    assert event.value == 45.0


def test_normalize_returns_none_for_missing_position():
    storm = SAMPLE_STORM.model_copy(update={"latitudeNumeric": None, "longitudeNumeric": None})
    assert normalize_storm(storm) is None


def test_normalize_returns_none_for_missing_intensity():
    storm = SAMPLE_STORM.model_copy(update={"intensity": None})
    assert normalize_storm(storm) is None


def test_normalize_returns_none_for_missing_timestamp():
    storm = SAMPLE_STORM.model_copy(update={"lastUpdate": None})
    assert normalize_storm(storm) is None


def test_each_advisory_gets_its_own_event_id():
    """Two advisories for the same storm must not overwrite each other (keeps the track)."""
    later = SAMPLE_STORM.model_copy(update={
        "lastUpdate": "2024-08-05T21:00:00-04:00",
        "latitudeNumeric": 30.4,
    })
    first, second = normalize_storm(SAMPLE_STORM), normalize_storm(later)
    assert first.event_id != second.event_id
    assert second.event_id == "nhc-al052024-202408060100"


def test_event_id_is_deterministic():
    assert normalize_storm(SAMPLE_STORM).event_id == normalize_storm(SAMPLE_STORM).event_id


def test_normalize_storms_batch():
    events = normalize_storms([SAMPLE_STORM, SAMPLE_TS])
    assert len(events) == 2
    types = {e.event_type for e in events}
    assert "hurricane" in types
    assert "tropical_storm" in types


# ---------------------------------------------------------------------------
# Client + live integration
# ---------------------------------------------------------------------------

def test_live_client_returns_list():
    """
    Fetch live storms. Empty list is valid off-season — just confirms the
    endpoint responds and the schema parses without error.
    """
    storms = fetch_active_storms()
    print(f"\n=== Active storms right now: {len(storms)} ===")
    if storms:
        for s in storms:
            print(f"  {s.name} ({s.classification}) — {s.latitudeNumeric}N, {s.longitudeNumeric}W — {s.intensity}kt")
    else:
        print("  (no active named storms — off-season or quiet period)")
    assert isinstance(storms, list)


def test_live_normalize_active_storms():
    """
    If storms are active, confirm they normalize to valid EarthEvents.
    Passes trivially when storm list is empty.
    """
    storms = fetch_active_storms()
    events = normalize_storms(storms)
    print(f"\n=== {len(events)} hurricane events from live feed ===")
    for e in events:
        print(json.dumps(e.model_dump(mode="json"), indent=2))
    assert len(events) == len(storms)  # every active storm should normalize cleanly
