from __future__ import annotations

import time
from typing import List, Optional

import httpx

from sources.usgs.schema import USGSFeature, USGSFeatureCollection

BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
MAX_RETRIES = 3
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def fetch_earthquakes(
    min_magnitude: float = 2.5,
    limit: int = 1000,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> List[USGSFeature]:
    """
    Fetch recent earthquake events from the USGS FDSN Event Web Service.

    Args:
        min_magnitude: minimum magnitude to include (default 2.5)
        limit: max events to fetch (max 20000)
        start: ISO8601 start time, e.g. "2026-08-01T00:00:00"
        end: ISO8601 end time

    Returns:
        List of USGSFeature, filtered to type="earthquake" only.

    Raises:
        RuntimeError: if all retries are exhausted
        httpx.HTTPStatusError: for non-retryable HTTP errors
    """
    params: dict = {
        "format": "geojson",
        "minmagnitude": min_magnitude,
        "orderby": "time",
        "eventtype": "earthquake",
        "limit": limit,
    }
    if start:
        params["starttime"] = start
    if end:
        params["endtime"] = end

    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.get(BASE_URL, params=params, timeout=30)
            if resp.status_code in RETRYABLE_STATUSES:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            collection = USGSFeatureCollection.model_validate(resp.json())
            return collection.features
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            time.sleep(2 ** attempt)

    raise RuntimeError(
        f"USGS API failed after {MAX_RETRIES} attempts"
    ) from last_exc
