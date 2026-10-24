"""Trigger dbt after a successful load without re-running API ingest."""

from __future__ import annotations

from dagster import (
    AssetKey,
    DagsterRunStatus,
    DefaultSensorStatus,
    RunRequest,
    SensorEvaluationContext,
    SkipReason,
    asset_sensor,
)

from lahore_aqi_dagster.jobs.pipeline import dbt_only_job, full_pipeline_job


def _job_is_active(context: SensorEvaluationContext, job_name: str) -> bool:
    active = {
        DagsterRunStatus.STARTED,
        DagsterRunStatus.STARTING,
        DagsterRunStatus.QUEUED,
        DagsterRunStatus.CANCELING,
    }
    for run in context.instance.get_runs(limit=30):
        if run.job_name == job_name and run.status in active:
            return True
    return False


@asset_sensor(
    asset_key=AssetKey(["ingestion", "raw_observations_loaded"]),
    job=dbt_only_job,
    default_status=DefaultSensorStatus.STOPPED,
    minimum_interval_seconds=60,
    description=(
        "When raw observations are loaded, run dbt + quality checks. "
        "Skips if dbt_only_job or full_pipeline_job is already active "
        "(avoids duplicate transforms)."
    ),
)
def dbt_after_load_sensor(context: SensorEvaluationContext, asset_event):
    if _job_is_active(context, dbt_only_job.name):
        return SkipReason("dbt_only_job already active")
    if _job_is_active(context, full_pipeline_job.name):
        return SkipReason("full_pipeline_job already active — dbt included there")

    run_key = f"dbt-after-load-{asset_event.run_id}-{asset_event.timestamp}"
    context.log.info(
        "sensor_trigger_dbt asset=raw_observations_loaded run_key=%s",
        run_key,
    )
    return RunRequest(run_key=run_key)
