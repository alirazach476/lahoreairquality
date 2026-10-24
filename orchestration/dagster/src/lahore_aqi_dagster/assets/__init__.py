"""Dagster assets for the Lahore AQI pipeline (no ML)."""

from lahore_aqi_dagster.assets.ingestion import raw_events_published
from lahore_aqi_dagster.assets.loading import raw_observations_loaded
from lahore_aqi_dagster.assets.quality import data_quality_checks
from lahore_aqi_dagster.assets.transforms import dbt_models

ALL_ASSETS = [
    raw_events_published,
    raw_observations_loaded,
    dbt_models,
    data_quality_checks,
]

__all__ = [
    "ALL_ASSETS",
    "data_quality_checks",
    "dbt_models",
    "raw_events_published",
    "raw_observations_loaded",
]
