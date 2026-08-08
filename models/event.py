from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class EarthEvent(BaseModel):
    event_id: str
    event_type: str
    observed_at: datetime
    latitude: float
    longitude: float
    region: str
    value: float
    unit: str
    origin: Literal["observed", "derived", "simulated"]
    source: str
    confidence: float
    ingested_at: datetime
