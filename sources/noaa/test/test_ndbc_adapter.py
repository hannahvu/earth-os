"""
NDBC adapter tests.

Run via PyCharm run button or:
    uv run pytest sources/noaa/test/test_ndbc_adapter.py -s
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from sources.noaa.ndbc.client import fetch_all_priority_stations, fetch_station_text
from sources.noaa.ndbc.normalize import normalize_all, normalize_station
from sources.noaa.ndbc.schema import FIELD_MAP, extract_measurements, parse_latest_row, parse_rows
from sources.noaa.ndbc.stations import get_priority_stations


# ---------------------------------------------------------------------------
# Stations metadata
# ---------------------------------------------------------------------------

def test_station_metadata_loads():
    """Priority stations resolve to lat/lon from NDBC station table."""
    stations = get_priority_stations()
    print(f"\n=== {len(stations)} priority stations resolved ===")
    for sid, meta in list(stations.items())[:5]:
        print(f"  {sid}: {meta['name']}  ({meta['lat']}, {meta['lon']})")
    assert len(stations) > 0
    for sid, meta in stations.items():
        assert -90 <= meta["lat"] <= 90, f"{sid} lat out of range"
        assert -180 <= meta["lon"] <= 180, f"{sid} lon out of range"


# ---------------------------------------------------------------------------
# Schema — parsing
# ---------------------------------------------------------------------------

SAMPLE_TEXT = """\
#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE
#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   hPa  degC  degC  degC  nmi  hPa    ft
2026 08 08 22 50 310  9.0 10.0   1.1    16   4.9 216 1012.6  17.6  19.7  16.3   MM   MM    MM
2026 08 08 22 40 310  9.0 11.0   1.1    MM   4.9 216 1012.6  17.7  19.7  16.5   MM   MM    MM
"""

def test_parse_latest_row():
    row = parse_latest_row(SAMPLE_TEXT)
    assert row is not None
    assert row["YY"] == "2026"
    assert row["WTMP"] == "19.7"
    assert row["VIS"] == "MM"


def test_extract_measurements_skips_mm():
    row = parse_latest_row(SAMPLE_TEXT)
    measurements = extract_measurements(row)
    assert "WTMP" in measurements
    assert measurements["WTMP"] == 19.7
    assert "VIS" not in measurements   # MM — should be skipped
    assert "TIDE" not in measurements  # MM — should be skipped


def test_parse_returns_none_for_bad_text():
    assert parse_latest_row("") is None
    assert parse_latest_row("just one line") is None
    assert parse_rows("") == []


def _multi_row_text(n: int, start: datetime) -> str:
    """n rows at 10-minute spacing, newest first, matching realtime2 format."""
    header = SAMPLE_TEXT.splitlines()[:2]
    rows = []
    for i in range(n):
        t = start - timedelta(minutes=10 * i)
        rows.append(f"{t:%Y %m %d %H %M} 310  9.0 10.0   1.1    16   4.9 216 1012.6  17.6  19.7  16.3   MM   MM    MM")
    return "\n".join(header + rows) + "\n"


MULTI_START = datetime(2026, 8, 8, 23, 50, tzinfo=timezone.utc)
MULTI_TEXT = _multi_row_text(12, MULTI_START)  # 23:50 back to 22:00


def test_parse_rows_returns_all_rows_newest_first():
    rows = parse_rows(MULTI_TEXT)
    assert len(rows) == 12
    assert (rows[0]["hh"], rows[0]["mm"]) == ("23", "50")
    assert (rows[-1]["hh"], rows[-1]["mm"]) == ("22", "00")


def test_parse_rows_skips_malformed_rows():
    text = SAMPLE_TEXT + "2026 08 08 22 30 310 9.0\n"  # truncated row
    assert len(parse_rows(text)) == 2


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def test_fetch_single_station():
    """Fetch realtime text for one known active buoy."""
    text = fetch_station_text("46047")
    assert text is not None
    lines = text.strip().splitlines()
    print(f"\n=== 46047 — {len(lines)} lines, first 3: ===")
    for l in lines[:3]:
        print(" ", l)
    assert len(lines) >= 3


def test_fetch_inactive_station_returns_none():
    """Inactive or non-existent station should return None, not raise."""
    result = fetch_station_text("99999")
    assert result is None


def test_fetch_all_priority_stations():
    """Fetch all priority stations, report how many responded."""
    results = fetch_all_priority_stations()
    print(f"\n=== {len(results)} / {len(get_priority_stations())} stations responded ===")
    for sid, text in list(results.items())[:3]:
        row = parse_latest_row(text)
        wtmp = row.get("WTMP", "MM") if row else "?"
        print(f"  {sid}: WTMP={wtmp}°C")
    assert len(results) > 0


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------

def test_normalize_station_produces_events():
    """One station's text -> multiple EarthEvents, one per measurement type."""
    from models.event import EarthEvent

    events = normalize_station(
        station_id="46047",
        lat=32.4,
        lon=-119.5,
        name="NE Pacific",
        text=SAMPLE_TEXT,
    )

    print(f"\n=== {len(events)} events from sample text ===")
    for e in events:
        print(f"  {e.event_type}: {e.value} {e.unit}")
        print(f"  {json.dumps(e.model_dump(mode='json'), indent=2)}")
        break  # just show first

    assert len(events) > 0
    assert all(isinstance(e, EarthEvent) for e in events)
    assert all(e.source == "NDBC" for e in events)
    assert all(e.origin == "observed" for e in events)
    assert all(e.latitude == 32.4 for e in events)
    assert all(e.observed_at.tzinfo is not None for e in events)

    # One event per non-MM field in FIELD_MAP
    event_types = {e.event_type for e in events}
    assert "sea_surface_temperature" in event_types
    assert "wave_height" in event_types


def test_normalize_skips_mm_fields():
    """VIS and TIDE are MM in sample — no events for those types."""
    events = normalize_station("46047", 32.4, -119.5, "NE Pacific", SAMPLE_TEXT)
    event_types = {e.event_type for e in events}
    assert "visibility" not in event_types


def test_normalize_event_ids_are_deterministic():
    """Same input always produces the same event_id."""
    events_a = normalize_station("46047", 32.4, -119.5, "NE Pacific", SAMPLE_TEXT)
    events_b = normalize_station("46047", 32.4, -119.5, "NE Pacific", SAMPLE_TEXT)
    ids_a = {e.event_id for e in events_a}
    ids_b = {e.event_id for e in events_b}
    assert ids_a == ids_b


def test_normalize_station_emits_every_row():
    events = normalize_station("46047", 32.4, -119.5, "NE Pacific", MULTI_TEXT)
    fields_per_row = len(extract_measurements(parse_latest_row(MULTI_TEXT)))
    assert len(events) == 12 * fields_per_row
    assert len({e.observed_at for e in events}) == 12
    assert len({e.event_id for e in events}) == len(events)


def test_normalize_station_respects_cutoff():
    cutoff = datetime(2026, 8, 8, 23, 0, tzinfo=timezone.utc)
    events = normalize_station("46047", 32.4, -119.5, "NE Pacific", MULTI_TEXT, cutoff=cutoff)
    times = {e.observed_at for e in events}
    assert len(times) == 6  # 23:50, 23:40, ... 23:00 (cutoff is inclusive)
    assert min(times) == cutoff


def test_overlapping_windows_produce_identical_ids():
    """Re-ingesting an overlapping window yields the same IDs, so MERGE dedups it."""
    a = normalize_station("46047", 32.4, -119.5, "NE Pacific", MULTI_TEXT,
                          cutoff=datetime(2026, 8, 8, 23, 0, tzinfo=timezone.utc))
    b = normalize_station("46047", 32.4, -119.5, "NE Pacific", MULTI_TEXT,
                          cutoff=datetime(2026, 8, 8, 22, 30, tzinfo=timezone.utc))
    assert {e.event_id for e in a} <= {e.event_id for e in b}


def test_full_pipeline():
    """fetch_all -> normalize_all -> EarthEvents for all active stations."""
    station_texts = fetch_all_priority_stations()
    events = normalize_all(station_texts)

    sources = {e.source for e in events}
    event_types = {e.event_type for e in events}

    print(f"\n=== Full pipeline: {len(events)} events from {len(station_texts)} stations ===")
    print(f"  event types: {event_types}")

    assert len(events) > 0
    assert sources == {"NDBC"}
    assert "sea_surface_temperature" in event_types
