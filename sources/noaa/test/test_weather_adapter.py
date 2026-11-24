"""
NWS weather adapter tests.

Run via PyCharm run button or:
    uv run pytest sources/noaa/test/test_weather_adapter.py -s
"""
from __future__ import annotations

import json

import pytest

from datetime import datetime, timezone

import sources.noaa.weather.client as nws_client
from sources.noaa.weather.client import (
    BA_CENTROIDS,
    fetch_all_ba_observations,
    fetch_observation,
    observations_url,
)
from sources.noaa.weather.normalize import normalize_all, normalize_observation
from sources.noaa.weather.schema import (
    FIELD_MAP,
    NWSObservation,
    NWSObservationProperties,
    NWSQuantitativeValue,
)


# ---------------------------------------------------------------------------
# Synthetic observation for unit tests
# ---------------------------------------------------------------------------

def _make_obs(temperature: float = 35.0, timestamp: str = "2026-08-08T22:55:00+00:00") -> NWSObservation:
    return NWSObservation(
        properties=NWSObservationProperties(
            stationId="KBBD",
            stationName="Brady, Curtis Field Airport",
            timestamp=timestamp,
            temperature=NWSQuantitativeValue(value=temperature, unitCode="wmoUnit:degC"),
            dewpoint=NWSQuantitativeValue(value=14.0, unitCode="wmoUnit:degC"),
            relativeHumidity=NWSQuantitativeValue(value=28.4, unitCode="wmoUnit:percent"),
            windSpeed=NWSQuantitativeValue(value=12.96, unitCode="wmoUnit:km_h-1"),
            windDirection=NWSQuantitativeValue(value=190.0, unitCode="wmoUnit:degree_(angle)"),
            barometricPressure=NWSQuantitativeValue(value=101630.0, unitCode="wmoUnit:Pa"),
            visibility=NWSQuantitativeValue(value=16090.0, unitCode="wmoUnit:m"),
            heatIndex=NWSQuantitativeValue(value=34.4, unitCode="wmoUnit:degC"),
            windGust=NWSQuantitativeValue(value=None, unitCode="wmoUnit:km_h-1"),  # null
            windChill=NWSQuantitativeValue(value=None, unitCode="wmoUnit:degC"),   # null
            precipitationLastHour=NWSQuantitativeValue(value=None, unitCode="wmoUnit:mm"),
        )
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_field_map_has_temperature():
    assert "temperature" in FIELD_MAP
    event_type, unit = FIELD_MAP["temperature"]
    assert event_type == "air_temperature"
    assert unit == "degC"


def test_observation_parses():
    obs = _make_obs()
    assert obs.properties.temperature is not None
    assert obs.properties.temperature.value == 35.0


# ---------------------------------------------------------------------------
# Normalize — unit tests
# ---------------------------------------------------------------------------

def test_normalize_produces_events():
    obs = _make_obs()
    events = normalize_observation(
        ba="ERCO",
        station_id="KBBD",
        lat=31.5,
        lon=-99.3,
        obs=obs,
    )

    print(f"\n=== {len(events)} events from synthetic ERCO observation ===")
    for e in events:
        print(f"  {e.event_type}: {e.value} {e.unit}")

    assert len(events) > 0
    types = {e.event_type for e in events}
    assert "air_temperature" in types
    assert "relative_humidity" in types


def test_normalize_skips_null_values():
    """windGust, windChill, precipitationLastHour are null — should be excluded."""
    obs = _make_obs()
    events = normalize_observation("ERCO", "KBBD", 31.5, -99.3, obs)
    types = {e.event_type for e in events}
    assert "wind_gust" not in types
    assert "wind_chill" not in types
    assert "precipitation_1h" not in types


def test_normalize_event_fields():
    obs = _make_obs()
    events = normalize_observation("ERCO", "KBBD", 31.5, -99.3, obs)
    temp_event = next(e for e in events if e.event_type == "air_temperature")

    assert temp_event.event_id.startswith("nws-erco-kbbd-")
    assert temp_event.region == "ERCO"
    assert temp_event.value == 35.0
    assert temp_event.unit == "degC"
    assert temp_event.source == "NWS"
    assert temp_event.origin == "observed"
    assert temp_event.latitude == 31.5
    assert temp_event.observed_at.tzinfo is not None

    print(f"\n=== Sample temperature event ===")
    import json
    print(json.dumps(temp_event.model_dump(mode="json"), indent=2))


def test_normalize_missing_timestamp_returns_empty():
    obs = NWSObservation(properties=NWSObservationProperties(timestamp=None))
    events = normalize_observation("ERCO", "KBBD", 31.5, -99.3, obs)
    assert events == []


def test_normalize_all_handles_multiple_observations():
    obs_list = [
        _make_obs(timestamp="2026-08-08T22:55:00+00:00"),
        _make_obs(timestamp="2026-08-08T22:50:00+00:00"),
        _make_obs(timestamp="2026-08-08T21:55:00+00:00"),
    ]
    events = normalize_all({"ERCO": ("KBBD", obs_list)}, BA_CENTROIDS)
    temps = [e for e in events if e.event_type == "air_temperature"]
    assert len({e.observed_at for e in temps}) == 3
    assert len({e.event_id for e in events}) == len(events)  # no ID collisions across observations


# ---------------------------------------------------------------------------
# Client — unit
# ---------------------------------------------------------------------------

def test_observations_url_uses_utc_z():
    from datetime import timedelta
    start = datetime(2026, 8, 8, 17, 0, tzinfo=timezone(timedelta(hours=-5)))
    url = observations_url("KBBD", start)
    assert url == "https://api.weather.gov/stations/KBBD/observations?start=2026-08-08T22:00:00Z"


def test_station_lookup_is_cached(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        if "/points/" in url:
            return {"properties": {"observationStations": "https://example/stations"}}
        return {"features": [{"properties": {"stationIdentifier": "KTEST"}}]}

    monkeypatch.setattr(nws_client, "_get", fake_get)
    monkeypatch.setattr(nws_client, "_station_cache", {})

    assert nws_client._nearest_station_id(1.0, 2.0) == "KTEST"
    assert nws_client._nearest_station_id(1.0, 2.0) == "KTEST"
    assert len(calls) == 2  # points + stations, once


def test_failed_station_lookup_not_cached(monkeypatch):
    def failing_get(url):
        raise RuntimeError("down")

    monkeypatch.setattr(nws_client, "_get", failing_get)
    monkeypatch.setattr(nws_client, "_station_cache", {})

    assert nws_client._nearest_station_id(1.0, 2.0) is None
    assert nws_client._station_cache == {}


# ---------------------------------------------------------------------------
# Client + live integration
# ---------------------------------------------------------------------------

def test_fetch_single_ba():
    """Fetch latest observation for ERCO centroid."""
    result = fetch_observation("ERCO")
    assert result is not None
    ba, station_id, obs = result

    print(f"\n=== Live observation for ERCO from {station_id} ===")
    props = obs.properties
    print(f"  timestamp: {props.timestamp}")
    if props.temperature:
        print(f"  temperature: {props.temperature.value}°C")
    if props.relativeHumidity:
        print(f"  humidity: {props.relativeHumidity.value}%")
    if props.heatIndex and props.heatIndex.value:
        print(f"  heat index: {props.heatIndex.value}°C")

    assert ba == "ERCO"
    assert obs.properties.timestamp is not None


def test_fetch_all_bas():
    """Fetch observations for all 5 BA centroids."""
    results = fetch_all_ba_observations()
    print(f"\n=== Weather observations for {len(results)}/5 BAs ===")
    for ba, (station_id, obs_list) in results.items():
        print(f"  {ba}: station={station_id}  {len(obs_list)} observations in lookback window")
    assert len(results) > 0
    # Stations report every ~5-60 min, so a 6h window returns more than just the latest
    assert any(len(obs_list) > 1 for _, obs_list in results.values())


def test_full_pipeline():
    """fetch_all -> normalize_all -> EarthEvents."""
    from models.event import EarthEvent

    observations = fetch_all_ba_observations()
    events = normalize_all(observations, BA_CENTROIDS)

    sources = {e.source for e in events}
    event_types = {e.event_type for e in events}

    print(f"\n=== Full NWS pipeline: {len(events)} events from {len(observations)} BAs ===")
    print(f"  event types: {event_types}")

    assert len(events) > 0
    assert sources == {"NWS"}
    assert "air_temperature" in event_types
    assert all(isinstance(e, EarthEvent) for e in events)
