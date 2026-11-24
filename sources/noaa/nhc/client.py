from __future__ import annotations

import time
from typing import List, Optional

import httpx

from sources.noaa.nhc.schema import NHCCurrentStorms, NHCStorm

CURRENT_STORMS_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"
MAX_RETRIES = 3
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def fetch_active_storms() -> List[NHCStorm]:
    """
    Fetch currently active named storms from NHC.
    Returns an empty list during off-season or when no storms are active.

    Raises:
        RuntimeError: if all retries are exhausted
    """
    last_exc: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.get(CURRENT_STORMS_URL, timeout=30)
            if resp.status_code in RETRYABLE_STATUSES:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return NHCCurrentStorms.model_validate(resp.json()).activeStorms
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            time.sleep(2 ** attempt)

    raise RuntimeError(
        f"NHC API failed after {MAX_RETRIES} attempts"
    ) from last_exc
