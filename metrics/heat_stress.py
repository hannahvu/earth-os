"""
Heat stress index metric.

Joins NWS air temperature observations with EIA demand readings per BA.
Computes a heat stress score: how much demand is elevated relative to baseline
given the current temperature. High temperature + high demand = grid stress.

Formula: heat_stress = (temp_C - BASELINE_TEMP) * (demand / mean_demand)
  - Positive and large: hot day + above-average demand (grid stress)
  - Near zero: mild temperature or normal demand
  - Negative: cool day with below-average demand

origin = "derived", source = "EarthOS"
value  = heat_stress score (dimensionless index)
unit   = "index"
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import polars as pl

from metrics.loader import load_events_df
from models.event import EarthEvent

BASELINE_TEMP_C = 20.0  # reference temperature for neutral demand


def _parse_ts(ts_val) -> datetime:
    if isinstance(ts_val, datetime):
        return ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(ts_val)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_heat_stress() -> List[EarthEvent]:
    """Load NWS temperature + EIA demand from BigQuery and compute heat stress."""
    return heat_stress_from_dfs(
        load_events_df(source="NWS", event_type="air_temperature"),
        load_events_df(source="EIA", event_type="grid_demand"),
    )


def heat_stress_from_dfs(temp_df: pl.DataFrame, demand_df: pl.DataFrame) -> List[EarthEvent]:
    """
    Returns one derived EarthEvent per BA where both temperature and
    demand observations are available.
    """
    if temp_df.is_empty() or demand_df.is_empty():
        return []

    # Latest temperature per BA
    latest_temp = (
        temp_df
        .sort("observed_at", descending=True)
        .group_by("region")
        .agg(
            pl.col("value").first().alias("temperature"),
            pl.col("observed_at").first().alias("temp_ts"),
        )
    )

    # Latest demand and mean demand per BA
    demand_stats = demand_df.group_by("region").agg(
        pl.col("value").mean().alias("mean_demand"),
        pl.col("latitude").first(),
        pl.col("longitude").first(),
    )
    latest_demand = (
        demand_df
        .sort("observed_at", descending=True)
        .group_by("region")
        .agg(
            pl.col("value").first().alias("demand"),
            pl.col("observed_at").first().alias("demand_ts"),
        )
    )

    # Join everything on BA region
    joined = (
        latest_temp
        .join(latest_demand, on="region")
        .join(demand_stats, on="region")
        .with_columns(
            (
                (pl.col("temperature") - BASELINE_TEMP_C)
                * (pl.col("demand") / pl.col("mean_demand"))
            ).alias("heat_stress")
        )
    )

    if joined.is_empty():
        return []

    now = datetime.now(tz=timezone.utc)
    events: List[EarthEvent] = []

    for row in joined.iter_rows(named=True):
        observed_at = _parse_ts(row["demand_ts"])
        ts = observed_at.strftime("%Y%m%d%H%M")

        events.append(EarthEvent(
            event_id=f"derived-heat-stress-{row['region'].lower()}-{ts}",
            event_type="heat_stress_index",
            observed_at=observed_at,
            latitude=row["latitude"],
            longitude=row["longitude"],
            region=row["region"],
            value=round(row["heat_stress"], 3),
            unit="index",
            origin="derived",
            source="EarthOS",
            confidence=0.75,
            ingested_at=now,
        ))

    return events
