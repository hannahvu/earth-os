"""
Exploration: NOAA api.weather.gov — US weather observations.
No API key required. NWS requires a User-Agent header with contact info.

Run:
    uv run pytest sources/noaa/test/test_weather_api.py -s
"""
import json

import httpx
import pytest

BASE_URL = "https://api.weather.gov"
HEADERS = {"User-Agent": "EarthOS/0.2 (https://github.com/hannahvu/earth-os)"}

# BA centroids — we want weather observations near each grid region
BA_CENTROIDS = {
    "ERCO": (31.5, -99.3),   # central Texas
    "CISO": (37.0, -120.0),  # central California
    "PJM":  (40.0, -77.0),   # mid-Atlantic
}


def get_points(lat: float, lon: float) -> dict:
    resp = httpx.get(f"{BASE_URL}/points/{lat},{lon}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def test_points_endpoint_shape():
    """
    /points/{lat},{lon} — returns gridpoint metadata and URLs for
    forecasts, observation stations, etc. This is the entry point for
    everything else in the NWS API.
    """
    lat, lon = BA_CENTROIDS["ERCO"]
    data = get_points(lat, lon)

    print("\n=== /points top-level keys ===")
    print(list(data.keys()))

    props = data.get("properties", {})
    print("\n=== properties keys ===")
    print(list(props.keys()))

    print("\n=== key URLs in properties ===")
    url_keys = [k for k, v in props.items() if isinstance(v, str) and v.startswith("http")]
    for k in url_keys:
        print(f"  {k}: {props[k]}")

    print("\n=== full properties ===")
    print(json.dumps(props, indent=2))

    assert "properties" in data
    assert "observationStations" in props


def test_observation_stations_near_bas():
    """
    Get the list of NWS observation stations near each BA centroid.
    Shows station IDs, names, and coordinates.
    """
    for ba, (lat, lon) in BA_CENTROIDS.items():
        points = get_points(lat, lon)
        stations_url = points["properties"]["observationStations"]

        resp = httpx.get(stations_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        features = resp.json().get("features", [])

        print(f"\n=== Stations near {ba} ({lat}, {lon}) — {len(features)} found ===")
        for s in features[:5]:
            props = s.get("properties", {})
            coords = s.get("geometry", {}).get("coordinates", [])
            print(f"  {props.get('stationIdentifier')} — {props.get('name')} {coords}")

        assert len(features) > 0


def test_latest_observation_shape():
    """
    Fetch the latest observation from the nearest station to ERCO.
    Shows full observation properties — what fields exist, types, units.
    """
    points = get_points(*BA_CENTROIDS["ERCO"])
    stations_url = points["properties"]["observationStations"]
    stations = httpx.get(stations_url, headers=HEADERS, timeout=30).json()
    station_id = stations["features"][0]["properties"]["stationIdentifier"]

    obs_resp = httpx.get(
        f"{BASE_URL}/stations/{station_id}/observations/latest",
        headers=HEADERS,
        timeout=30,
    )
    obs_resp.raise_for_status()
    obs = obs_resp.json()

    props = obs.get("properties", {})
    print(f"\n=== Latest observation from {station_id} ===")
    print(json.dumps(props, indent=2))

    print("\n=== Numeric fields with units (quantitative values) ===")
    for k, v in props.items():
        if isinstance(v, dict) and "value" in v:
            print(f"  {k}: {v.get('value')} {v.get('unitCode', '')}")

    assert "temperature" in props
