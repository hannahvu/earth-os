from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx

from sources.lookback import lookback_cutoff
from sources.noaa.weather.schema import (
    NWS_HEADERS,
    NWSObservation,
    NWSObservationCollection,
    NWSStationsResponse,
)

BASE_URL = "https://api.weather.gov"
MAX_PAGES = 10  # 500 observations per page; 7 days at 5-min reporting is ~2 pages
MAX_RETRIES = 3
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# BA centroids — one nearest station fetched per BA
BA_CENTROIDS: Dict[str, Tuple[float, float]] = {
    "ERCO": (31.5, -99.3),
    "CISO": (37.0, -120.0),
    "PJM":  (40.0, -77.0),
    "MISO": (44.0, -90.0),
    "ISNE": (43.0, -71.5),
}

# (lat, lon) -> station_id. Only successful lookups are cached, so a
# transient failure is retried on the next call instead of sticking.
_station_cache: Dict[Tuple[float, float], str] = {}


def _get(url: str) -> dict:
    """GET with retries. Raises RuntimeError after MAX_RETRIES failures."""
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.get(url, headers=NWS_HEADERS, timeout=30)
            if resp.status_code in RETRYABLE_STATUSES:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"NWS request failed after {MAX_RETRIES} attempts: {url}") from last_exc


def observations_url(station_id: str, start: datetime) -> str:
    """Observations endpoint for a time range. `start` is sent as UTC with a Z suffix."""
    iso = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{BASE_URL}/stations/{station_id}/observations?start={iso}"


def _obs_time(obs: NWSObservation) -> Optional[datetime]:
    ts = obs.properties.timestamp
    try:
        return datetime.fromisoformat(ts).astimezone(timezone.utc) if ts else None
    except ValueError:
        return None


def observations_since(obs_list: List[NWSObservation], start: datetime) -> List[NWSObservation]:
    """Keep observations at or after `start` (pagination can run past it)."""
    return [o for o in obs_list if (t := _obs_time(o)) is not None and t >= start]


def page_reaches_start(page: List[NWSObservation], start: datetime) -> bool:
    """
    True once a page (newest first) includes anything older than `start`.
    The `next` cursor ignores `start` and keeps going into older data,
    so this is the stop condition.
    """
    times = [t for o in page if (t := _obs_time(o)) is not None]
    return bool(times) and min(times) < start


def _nearest_station_id(lat: float, lon: float) -> Optional[str]:
    """Resolve lat/lon -> nearest NWS observation station ID (3-step chain, cached)."""
    if (lat, lon) in _station_cache:
        return _station_cache[(lat, lon)]
    try:
        points_data = _get(f"{BASE_URL}/points/{lat},{lon}")
        stations_url = points_data["properties"]["observationStations"]
        stations_data = NWSStationsResponse.model_validate(_get(stations_url))
        if not stations_data.features:
            return None
        station_id = stations_data.features[0].properties.get("stationIdentifier")
    except (KeyError, RuntimeError):
        return None
    if station_id:
        _station_cache[(lat, lon)] = station_id
    return station_id


def fetch_observation(ba: str) -> Optional[Tuple[str, str, NWSObservation]]:
    """
    Fetch the latest observation for the nearest station to a BA centroid.

    Returns:
        (ba, station_id, NWSObservation) or None if station lookup fails.
    """
    lat, lon = BA_CENTROIDS[ba]
    station_id = _nearest_station_id(lat, lon)
    if not station_id:
        return None

    try:
        data = _get(f"{BASE_URL}/stations/{station_id}/observations/latest")
        obs = NWSObservation.model_validate(data)
        return ba, station_id, obs
    except (RuntimeError, Exception):
        return None


def fetch_observations(ba: str, start: datetime) -> Optional[Tuple[str, List[NWSObservation]]]:
    """
    Fetch every observation since `start` for the nearest station to a BA centroid.

    Returns:
        (station_id, observations newest-first) or None if the lookup or request fails.
    """
    lat, lon = BA_CENTROIDS[ba]
    station_id = _nearest_station_id(lat, lon)
    if not station_id:
        return None

    observations: List[NWSObservation] = []
    url: Optional[str] = observations_url(station_id, start)
    try:
        for _ in range(MAX_PAGES):
            data = _get(url)
            page = NWSObservationCollection.model_validate(data).features
            observations.extend(page)
            url = (data.get("pagination") or {}).get("next")
            if not page or not url or page_reaches_start(page, start):
                break
    except Exception:
        return None
    return station_id, observations_since(observations, start)


def fetch_all_ba_observations(
    start: Optional[datetime] = None,
) -> Dict[str, Tuple[str, List[NWSObservation]]]:
    """
    Fetch observations since `start` (default: shared lookback window) for all 5 BA centroids.
    Returns {ba: (station_id, observations)}, skipping any that fail.
    """
    start = start or lookback_cutoff()
    results: Dict[str, Tuple[str, List[NWSObservation]]] = {}
    for ba in BA_CENTROIDS:
        result = fetch_observations(ba, start)
        if result:
            results[ba] = result
    return results
