from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

# NHC storm classification codes -> event_type
CLASSIFICATION_MAP = {
    "HU": "hurricane",           # Hurricane
    "TS": "tropical_storm",      # Tropical Storm
    "TD": "tropical_depression", # Tropical Depression
    "SS": "subtropical_storm",
    "SD": "subtropical_depression",
    "EX": "extratropical_cyclone",
    "LO": "tropical_remnant",
    "DB": "tropical_disturbance",
}


class NHCAdvisoryLink(BaseModel):
    advNum: Optional[str] = None
    issuance: Optional[str] = None
    fileUpdateTime: Optional[str] = None
    url: Optional[str] = None


class NHCStorm(BaseModel):
    id: str                                      # e.g. "al052024"
    name: str                                    # e.g. "DEBBY"
    classification: str                          # e.g. "HU", "TS", "TD"
    intensity: Optional[str] = None             # max sustained winds in knots (string)
    pressure: Optional[str] = None              # central pressure in mb (string)
    latitude: Optional[str] = None              # e.g. "29.9N"
    longitude: Optional[str] = None             # e.g. "83.6W"
    latitudeNumeric: Optional[float] = None
    longitudeNumeric: Optional[float] = None
    movementDir: Optional[int] = None           # degrees
    movementSpeed: Optional[int] = None         # knots
    lastUpdate: Optional[str] = None            # ISO8601 string
    publicAdvisory: Optional[NHCAdvisoryLink] = None
    forecastAdvisory: Optional[NHCAdvisoryLink] = None
    windSpeedAdvisory: Optional[NHCAdvisoryLink] = None


class NHCCurrentStorms(BaseModel):
    activeStorms: List[NHCStorm] = []
