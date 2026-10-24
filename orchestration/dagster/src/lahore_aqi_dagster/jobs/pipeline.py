"""Jobs with concurrency limits to avoid duplicate overlapping runs."""

from __future__ import annotations

from dagster import (
    AssetSelection,
    define_asset_job,
)

# max_concurrent_runs=1 prevents stacking duplicate pipeline executions.
_TAG_SINGLETON = {"dagster/max_retries": "0"}  # asset-level retries still apply

ingest_and_load_job = define_asset_job(
    name="ingest_and_load_job",
    selection=AssetSelection.assets(
        ["ingestion", "raw_events_published"],
        ["ingestion", "raw_observations_loaded"],
    ),
    description=(
        "API poll → Redpanda publish → bounded consume → Postgres/S3 load. "
        "Does not run dbt (use dbt_only_job or full_pipeline_job)."
    ),
    tags={
        **_TAG_SINGLETON,
        "pipeline": "ingest_load",
    },
)

dbt_only_job = define_asset_job(
    name="dbt_only_job",
    selection=AssetSelection.assets(
        ["analytics", "dbt_models"],
        ["analytics", "data_quality_checks"],
    ),
    description="dbt seed/run + data-quality tests (no API poll).",
    tags={
        **_TAG_SINGLETON,
        "pipeline": "dbt",
    },
)

full_pipeline_job = define_asset_job(
    name="full_pipeline_job",
    selection=AssetSelection.groups("ingestion", "analytics"),
    description=(
        "End-to-end: ingest → load → dbt → quality checks. "
        "Preferred for manual / scheduled full runs."
    ),
    tags={
        **_TAG_SINGLETON,
        "pipeline": "full",
    },
)
