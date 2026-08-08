from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SourceConfig(BaseModel):
    source_id: str          # matches EarthEvent.source
    name: str
    description: str
    origin: Literal["observed", "derived", "simulated"]
    update_frequency_seconds: int   # how often the source publishes new data
    expected_lag_seconds: int       # typical delay between observation and publication
    confidence: float               # default confidence assigned to events from this source
