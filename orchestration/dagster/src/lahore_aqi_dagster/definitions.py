"""Dagster Definitions entrypoint for the Lahore AQI orchestration layer.

Pipeline (no ML):
  API ingestion → Redpanda publish/consume → Postgres/S3 load → dbt → quality checks
"""

from __future__ import annotations

from dagster import Definitions, load_assets_from_modules

import lahore_aqi_dagster.assets as assets_module
from lahore_aqi_dagster.jobs import dbt_only_job, full_pipeline_job, ingest_and_load_job
from lahore_aqi_dagster.resources import (
    AppSettingsResource,
    DbtResource,
    PipelineConfigResource,
)
from lahore_aqi_dagster.schedules import full_pipeline_schedule, ingest_schedule
from lahore_aqi_dagster.sensors import dbt_after_load_sensor

defs = Definitions(
    assets=load_assets_from_modules([assets_module]),
    jobs=[ingest_and_load_job, dbt_only_job, full_pipeline_job],
    schedules=[ingest_schedule, full_pipeline_schedule],
    sensors=[dbt_after_load_sensor],
    resources={
        "app_settings": AppSettingsResource(),
        "pipeline_config": PipelineConfigResource(),
        "dbt": DbtResource(skip_if_unavailable=True),
    },
)
