from models.source_config import SourceConfig

USGS_SOURCE = SourceConfig(
    source_id="USGS",
    name="U.S. Geological Survey — Earthquake Hazards Program",
    description="Global earthquake events M2.5+ (FDSN Event Web Service)",
    origin="observed",
    update_frequency_seconds=60,      # automatic detections arrive within minutes
    expected_lag_seconds=300,         # ~5 min for automatic; hours for reviewed
    confidence=0.95,                  # reviewed events; automatic overridden to 0.7 in normalize
)
