from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

NWS_HEADERS = {"User-Agent": "EarthOS/0.3 (https://github.com/hannahvu/earth-os)"}

# Maps NWS observation property key -> (event_type, unit)
# Only fields with consistent, non-null values across US stations
FIELD_MAP: Dict[str, Tuple[str, str]] = {
    "temperature":          ("air_temperature",    "degC"),
    "dewpoint":             ("dewpoint",            "degC"),
    "windDirection":        ("wind_direction",      "degrees"),
    "windSpeed":            ("wind_speed",          "km/h"),
    "windGust":             ("wind_gust",           "km/h"),
    "barometricPressure":   ("barometric_pressure", "Pa"),
    "visibility":           ("visibility",          "m"),
    "relativeHumidity":     ("relative_humidity",   "percent"),
    "heatIndex":            ("heat_index",          "degC"),
    "windChill":            ("wind_chill",          "degC"),
    "precipitationLastHour":("precipitation_1h",   "mm"),
}


class NWSQuantitativeValue(BaseModel):
    value: Optional[float] = None
    unitCode: Optional[str] = None


class NWSObservationProperties(BaseModel):
    stationId: Optional[str] = None
    stationName: Optional[str] = None
    timestamp: Optional[str] = None
    temperature: Optional[NWSQuantitativeValue] = None
    dewpoint: Optional[NWSQuantitativeValue] = None
    windDirection: Optional[NWSQuantitativeValue] = None
    windSpeed: Optional[NWSQuantitativeValue] = None
    windGust: Optional[NWSQuantitativeValue] = None
    barometricPressure: Optional[NWSQuantitativeValue] = None
    visibility: Optional[NWSQuantitativeValue] = None
    relativeHumidity: Optional[NWSQuantitativeValue] = None
    heatIndex: Optional[NWSQuantitativeValue] = None
    windChill: Optional[NWSQuantitativeValue] = None
    precipitationLastHour: Optional[NWSQuantitativeValue] = None


class NWSObservation(BaseModel):
    properties: NWSObservationProperties


class NWSObservationCollection(BaseModel):
    """Response of /stations/{id}/observations?start=... — newest first."""
    features: List[NWSObservation] = []


class NWSStationFeature(BaseModel):
    properties: dict


class NWSStationsResponse(BaseModel):
    features: List[NWSStationFeature]
