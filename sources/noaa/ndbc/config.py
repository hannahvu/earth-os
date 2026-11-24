from models.source_config import SourceConfig

NDBC_SOURCE = SourceConfig(
    source_id="NDBC",
    name="NOAA National Data Buoy Center",
    description="Real-time ocean and atmospheric observations from moored buoys and C-MAN stations",
    origin="observed",
    update_frequency_seconds=600,   # buoys report every ~10 minutes
    expected_lag_seconds=600,       # data typically available within 10-15 min of observation
    confidence=0.90,                # reliable but occasional sensor failures occur
)
