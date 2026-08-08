from models.source_config import SourceConfig

EIA_SOURCE = SourceConfig(
    source_id="EIA",
    name="U.S. Energy Information Administration",
    description="Hourly electricity demand by balancing authority (Form EIA-930)",
    origin="observed",
    update_frequency_seconds=3600,   # EIA publishes new hourly rows each hour
    expected_lag_seconds=3600,       # data typically available ~1 hour after observation
    confidence=0.99,
)
