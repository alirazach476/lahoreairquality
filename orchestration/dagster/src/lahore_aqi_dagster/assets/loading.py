"""Assets: Redpanda consume → S3 + PostgreSQL load."""

from dagster import AssetKey, Backoff, Jitter, RetryPolicy, asset

from lahore_aqi_dagster.logging_utils import log_metrics, log_stage
from lahore_aqi_dagster.resources.pipeline import PipelineConfigResource
from lahore_aqi_dagster.resources.settings import AppSettingsResource
from lahore_aqi_dagster.stages.consume_load import run_consume_and_load

DB_RETRY = RetryPolicy(
    max_retries=3,
    delay=15,
    backoff=Backoff.EXPONENTIAL,
    jitter=Jitter.PLUS_MINUS,
)


@asset(
    key=AssetKey(["ingestion", "raw_observations_loaded"]),
    group_name="ingestion",
    deps=[AssetKey(["ingestion", "raw_events_published"])],
    description=(
        "Bounded Redpanda consumer drain into MinIO (raw JSON) and PostgreSQL "
        "(normalized rows). Retries on database / broker sink failures."
    ),
    retry_policy=DB_RETRY,
)
def raw_observations_loaded(
    context,
    app_settings: AppSettingsResource,
    pipeline_config: PipelineConfigResource,
):
    settings = app_settings.get_settings()
    max_messages = pipeline_config.resolved_consumer_max_messages()
    log_stage(
        context,
        "stage_started",
        stage="redpanda_consume_load",
        max_messages=max_messages,
        consumer_group=settings.redpanda_consumer_group,
    )
    result = run_consume_and_load(
        settings,
        max_messages=max_messages,
        idle_polls_before_stop=pipeline_config.consumer_idle_polls,
    )
    log_metrics(context, stage="redpanda_consume_load", metrics=result.metrics)
    log_stage(
        context,
        "stage_succeeded",
        stage="redpanda_consume_load",
        messages_handled=result.messages_handled,
    )
    context.add_output_metadata(
        {
            "messages_handled": result.messages_handled,
            "max_messages": result.max_messages,
            "processed": result.metrics.get("processed"),
            "rejected": result.metrics.get("rejected"),
            "failed": result.metrics.get("failed"),
            "duplicate": result.metrics.get("duplicate"),
        }
    )
    return {
        "metrics": result.metrics,
        "messages_handled": result.messages_handled,
    }
