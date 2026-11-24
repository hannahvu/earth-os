from models.source_config import SourceConfig

NWS_SOURCE = SourceConfig(
    source_id="NWS",
    name="NOAA National Weather Service",
    description="Hourly surface weather observations from ASOS/AWOS stations near BA centroids",
    origin="observed",
    update_frequency_seconds=3600,  # observations updated hourly
    expected_lag_seconds=3600,      # typically ~1 hour behind real-time
    confidence=0.95,
)
