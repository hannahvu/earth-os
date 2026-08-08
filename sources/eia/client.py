from __future__ import annotations

import os
import time
from typing import Optional

import httpx
from dotenv import load_dotenv

from sources.eia.schema import EIARawResponse, EIARow

load_dotenv()

BASE_URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
MAX_RETRIES = 3
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def fetch_demand(
    respondent: str,
    length: int = 100,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> list[EIARow]:
    """
    Fetch hourly actual demand rows for one balancing authority.

    Args:
        respondent: BA code, e.g. "ERCO"
        length: number of rows to fetch (max 5000)
        start: inclusive start period, e.g. "2026-01-01T00"
        end: inclusive end period, e.g. "2026-01-07T23"

    Returns:
        List of EIARow, already filtered to type="D" (actual demand).

    Raises:
        RuntimeError: if all retries are exhausted
        httpx.HTTPStatusError: for non-retryable HTTP errors
    """
    params: dict = {
        "api_key": os.environ["EIA_API_KEY"],
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": respondent,
        "facets[type][]": "D",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": length,
    }
    if start:
        params["start"] = start
    if end:
        params["end"] = end

    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.get(BASE_URL, params=params, timeout=30)
            if resp.status_code in RETRYABLE_STATUSES:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            parsed = EIARawResponse.model_validate(resp.json())
            return parsed.response.data
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            time.sleep(2 ** attempt)

    raise RuntimeError(
        f"EIA API failed after {MAX_RETRIES} attempts for respondent={respondent}"
    ) from last_exc
