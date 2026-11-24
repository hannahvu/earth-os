from __future__ import annotations

import time
from typing import Dict, Optional

import httpx

from sources.noaa.ndbc.stations import get_priority_stations

REALTIME_URL = "https://www.ndbc.noaa.gov/data/realtime2/{station_id}.txt"
MAX_RETRIES = 3
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def fetch_station_text(station_id: str) -> Optional[str]:
    """
    Fetch realtime observation text for one station.
    Returns None for 404 (inactive/offline station) or exhausted retries.
    """
    url = REALTIME_URL.format(station_id=station_id)
    last_exc: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            if resp.status_code in RETRYABLE_STATUSES:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.text
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            time.sleep(2 ** attempt)

    return None


def fetch_all_priority_stations() -> Dict[str, str]:
    """
    Fetch realtime text for all priority stations.
    Returns {station_id: raw_text}, silently skipping offline stations.
    """
    station_ids = list(get_priority_stations().keys())
    results: Dict[str, str] = {}

    for station_id in station_ids:
        text = fetch_station_text(station_id)
        if text:
            results[station_id] = text

    return results
