"""
Demand anomaly metric.

For each BA, computes the z-score of each hourly demand reading vs the
7-day same-hour-of-day average. Flags readings where |z_score| > threshold.

origin = "derived", source = "EarthOS"
value  = z_score (signed — positive = above average, negative = below)
unit   = "z_score"
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import polars as pl

from metrics.loader import load_events_df
from models.event import EarthEvent

Z_SCORE_THRESHOLD = 1.5  # flag readings > 1.5 std devs from same-hour mean


def _parse_ts(ts_val) -> datetime:
    if isinstance(ts_val, datetime):
        return ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(ts_val)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_demand_anomaly() -> List[EarthEvent]:
    """Load EIA demand from BigQuery and compute demand anomalies."""
    return demand_anomaly_from_df(load_events_df(source="EIA", event_type="grid_demand"))


def demand_anomaly_from_df(df: pl.DataFrame) -> List[EarthEvent]:
    """
    Returns derived EarthEvents for demand readings that are anomalously
    high or low compared to the same hour of day across all available data.
    """
    if df.is_empty():
        return []

    # Parse timestamps and extract hour-of-day (observed_at may be str or datetime)
    if df["observed_at"].dtype == pl.Utf8:
        df = df.with_columns(
            pl.col("observed_at")
              .str.to_datetime(format="%Y-%m-%dT%H:%M:%S%z", strict=False)
              .alias("ts")
        )
    else:
        df = df.with_columns(pl.col("observed_at").alias("ts"))
    df = df.with_columns(pl.col("ts").dt.hour().alias("hour_of_day"))

    # Compute per-(region, hour_of_day) mean and std across all available days
    stats = df.group_by(["region", "hour_of_day"]).agg(
        pl.col("value").mean().alias("mean_demand"),
        pl.col("value").std().alias("std_demand"),
        pl.col("value").count().alias("sample_count"),
    )

    # Join stats back and compute z-score
    df = df.join(stats, on=["region", "hour_of_day"]).filter(
        (pl.col("std_demand") > 0) & (pl.col("sample_count") >= 3)
    ).with_columns(
        ((pl.col("value") - pl.col("mean_demand")) / pl.col("std_demand"))
        .alias("z_score")
    )

    # Keep only anomalous readings
    anomalies = df.filter(pl.col("z_score").abs() > Z_SCORE_THRESHOLD)

    now = datetime.now(tz=timezone.utc)
    events: List[EarthEvent] = []

    for row in anomalies.iter_rows(named=True):
        observed_at = _parse_ts(row["observed_at"])
        ts = observed_at.strftime("%Y%m%d%H%M")

        events.append(EarthEvent(
            event_id=f"derived-demand-anomaly-{row['region'].lower()}-{ts}",
            event_type="demand_anomaly",
            observed_at=observed_at,
            latitude=row["latitude"],
            longitude=row["longitude"],
            region=row["region"],
            value=round(row["z_score"], 3),
            unit="z_score",
            origin="derived",
            source="EarthOS",
            confidence=0.80,
            ingested_at=now,
        ))

    return events
