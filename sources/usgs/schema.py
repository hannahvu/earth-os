from __future__ import annotations

from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


class USGSGeometry(BaseModel):
    type: str
    coordinates: Tuple[float, float, float]  # [longitude, latitude, depth_km]


class USGSProperties(BaseModel):
    mag: Optional[float] = None
    place: Optional[str] = None
    time: int                           # Unix milliseconds
    updated: int                        # Unix milliseconds
    tz: Optional[int] = None
    url: Optional[str] = None
    detail: Optional[str] = None
    felt: Optional[int] = None
    cdi: Optional[float] = None
    mmi: Optional[float] = None
    alert: Optional[str] = None
    status: str                         # "reviewed" or "automatic"
    tsunami: int
    sig: int
    net: str
    code: str
    ids: Optional[str] = None
    sources: Optional[str] = None
    types: Optional[str] = None
    nst: Optional[int] = None
    dmin: Optional[float] = None
    rms: Optional[float] = None
    gap: Optional[float] = None
    magType: Optional[str] = None
    type: str                           # "earthquake", "quarry blast", etc.
    title: Optional[str] = None


class USGSFeature(BaseModel):
    type: str
    id: str
    properties: USGSProperties
    geometry: USGSGeometry


class USGSMetadata(BaseModel):
    generated: int
    url: str
    title: str
    status: int
    api: str
    count: Optional[int] = None   # absent when eventtype filter is applied
    limit: Optional[int] = None
    offset: Optional[int] = None


class USGSFeatureCollection(BaseModel):
    type: str
    metadata: USGSMetadata
    features: List[USGSFeature]
    bbox: Optional[List[float]] = Field(default=None)
