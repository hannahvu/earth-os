from models.source_config import SourceConfig

NHC_SOURCE = SourceConfig(
    source_id="NHC",
    name="NOAA National Hurricane Center",
    description="Real-time active tropical storm and hurricane positions and intensity",
    origin="observed",
    update_frequency_seconds=10800,  # advisories issued every 3-6 hours
    expected_lag_seconds=0,          # CurrentStorms.json reflects latest advisory
    confidence=0.95,
)
