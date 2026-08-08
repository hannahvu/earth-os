"""
USGS adapter tests — no API key needed.

Run via PyCharm run button or:
    uv run pytest sources/usgs/test/test_usgs.py -s
"""
import json

import httpx
import pytest

from sources.usgs.client import fetch_earthquakes
from sources.usgs.normalize import normalize_feature, normalize_features
from sources.usgs.schema import USGSFeature, USGSFeatureCollection

BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def _fetch_raw(limit: int = 3) -> dict:
    resp = httpx.get(BASE_URL, params={
        "format": "geojson", "minmagnitude": 2.5,
        "orderby": "time", "limit": limit,
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Step 1 — exploration (kept for reference)
# ---------------------------------------------------------------------------

def test_raw_response_shape():
    """Print full raw response so we can read the GeoJSON schema."""
    raw = _fetch_raw(limit=3)

    print("\n=== Top-level keys ===")
    print(list(raw.keys()))

    print("\n=== metadata ===")
    print(json.dumps(raw.get("metadata", {}), indent=2))

    features = raw.get("features", [])
    if features:
        f = features[0]
        print("\n=== First feature.properties ===")
        print(json.dumps(f["properties"], indent=2))
        print("\n=== First feature.geometry ===")
        print(json.dumps(f["geometry"], indent=2))

    assert "features" in raw
    assert len(features) > 0


def test_field_types_and_nulls():
    """Check nullable fields, magType values, and status values across a sample."""
    raw = _fetch_raw(limit=10)
    features = raw.get("features", [])

    nullable_fields = set()
    seen_mag_types, seen_statuses = set(), set()
    for f in features:
        props = f["properties"]
        for key, val in props.items():
            if val is None:
                nullable_fields.add(key)
        if props.get("magType"):
            seen_mag_types.add(props["magType"])
        if props.get("status"):
            seen_statuses.add(props["status"])

    print(f"\n=== Nullable fields: {nullable_fields} ===")
    print(f"=== magType values: {seen_mag_types} ===")
    print(f"=== status values: {seen_statuses} ===")
    print(f"=== coordinates (first): {features[0]['geometry']['coordinates']} ===")
    assert len(features) > 0


# ---------------------------------------------------------------------------
# Step 2 — schema (Pydantic parsing)
# ---------------------------------------------------------------------------

def test_schema_parses_raw_response():
    """USGSFeatureCollection must parse the live API response without error."""
    raw = _fetch_raw(limit=5)
    collection = USGSFeatureCollection.model_validate(raw)

    print(f"\n=== Parsed {len(collection.features)} features ===")
    f = collection.features[0]
    print(f"  id={f.id}  mag={f.properties.mag}  status={f.properties.status}")
    print(f"  coords=[lon={f.geometry.coordinates[0]}, lat={f.geometry.coordinates[1]}, depth={f.geometry.coordinates[2]}km]")

    assert len(collection.features) > 0
    assert collection.features[0].properties.mag is not None


# ---------------------------------------------------------------------------
# Step 3 — client
# ---------------------------------------------------------------------------

def test_client_returns_usgs_features():
    """Client fetches and returns typed USGSFeature objects."""
    features = fetch_earthquakes(min_magnitude=2.5, limit=10)

    print(f"\n=== Fetched {len(features)} features ===")
    for f in features[:3]:
        print(f"  {f.id}  M{f.properties.mag}  {f.properties.place}")

    assert len(features) > 0
    assert all(isinstance(f, USGSFeature) for f in features)
    assert all(f.properties.type == "earthquake" for f in features)


# ---------------------------------------------------------------------------
# Step 4 — normalize
# ---------------------------------------------------------------------------

def test_normalize_produces_earth_events():
    """Full pipeline: fetch -> normalize -> EarthEvent with correct fields."""
    from models.event import EarthEvent

    features = fetch_earthquakes(min_magnitude=2.5, limit=10)
    events = normalize_features(features)

    print(f"\n=== {len(events)} EarthEvents ===")
    for e in events[:3]:
        print(json.dumps(e.model_dump(mode="json"), indent=2))

    assert len(events) > 0
    e = events[0]
    assert isinstance(e, EarthEvent)
    assert e.event_id.startswith("usgs-")
    assert e.event_type == "earthquake"
    assert e.origin == "observed"
    assert e.source == "USGS"
    assert e.latitude != 0.0
    assert e.longitude != 0.0
    assert e.value > 0
    assert e.observed_at.tzinfo is not None


def test_normalize_skips_null_magnitude():
    """normalize_feature must return None when mag is None."""
    raw = _fetch_raw(limit=1)
    collection = USGSFeatureCollection.model_validate(raw)
    feature = collection.features[0]

    feature.properties.mag = None
    assert normalize_feature(feature) is None


def test_normalize_confidence_by_status():
    """reviewed events get 0.95 confidence, automatic get 0.70."""
    raw = _fetch_raw(limit=1)
    collection = USGSFeatureCollection.model_validate(raw)
    feature = collection.features[0]

    feature.properties.status = "reviewed"
    reviewed = normalize_feature(feature)
    assert reviewed is not None and reviewed.confidence == 0.95

    feature.properties.status = "automatic"
    automatic = normalize_feature(feature)
    assert automatic is not None and automatic.confidence == 0.70
