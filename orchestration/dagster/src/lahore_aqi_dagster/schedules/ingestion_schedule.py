"""Periodic schedules aligned with poll interval (env-driven)."""

from __future__ import annotations

import os

from dagster import (
    DefaultScheduleStatus,
    RunRequest,
    ScheduleEvaluationContext,
    schedule,
)

from lahore_aqi_dagster.jobs.pipeline import full_pipeline_job, ingest_and_load_job


def _poll_cron() -> str:
    """Map POLL_INTERVAL_SECONDS to a simple cron (default every 5 minutes)."""
    raw = os.environ.get("DAGSTER_INGEST_CRON")
    if raw:
        return raw.strip()
    try:
        interval = float(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
    except ValueError:
        interval = 300.0
    if interval <= 60:
        return "* * * * *"
    if interval <= 300:
        return "*/5 * * * *"
    if interval <= 900:
        return "*/15 * * * *"
    return "0 * * * *"


def _should_skip_if_running(context: ScheduleEvaluationContext, job_name: str) -> bool:
    """Avoid duplicate runs when the same job is already active."""
    from dagster import DagsterRunStatus

    active = {
        DagsterRunStatus.STARTED,
        DagsterRunStatus.STARTING,
        DagsterRunStatus.QUEUED,
        DagsterRunStatus.CANCELING,
    }
    runs = context.instance.get_runs(limit=30)
    for run in runs:
        if run.job_name == job_name and run.status in active:
            context.log.info(
                "schedule_skip_duplicate job=%s run_id=%s status=%s",
                job_name,
                run.run_id,
                run.status,
            )
            return True
    return False


@schedule(
    job=ingest_and_load_job,
    cron_schedule=_poll_cron(),
    default_status=DefaultScheduleStatus.STOPPED,
    description=(
        "Poll APIs and load Redpanda → Postgres/S3. "
        "Stopped by default in local config — start in UI when stack is up."
    ),
)
def ingest_schedule(context: ScheduleEvaluationContext):
    if _should_skip_if_running(context, ingest_and_load_job.name):
        return
    return RunRequest(run_key=None)


@schedule(
    job=full_pipeline_job,
    cron_schedule=os.environ.get("DAGSTER_FULL_PIPELINE_CRON", "0 * * * *"),
    default_status=DefaultScheduleStatus.STOPPED,
    description=(
        "Hourly full pipeline (ingest → dbt → quality). "
        "Stopped by default; enable for unattended local/dev runs."
    ),
)
def full_pipeline_schedule(context: ScheduleEvaluationContext):
    if _should_skip_if_running(context, full_pipeline_job.name):
        return
    return RunRequest(run_key=None)
