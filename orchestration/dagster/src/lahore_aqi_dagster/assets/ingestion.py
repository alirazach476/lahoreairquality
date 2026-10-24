"""Assets: API ingestion → Redpanda publish."""

from dagster import AssetKey, Backoff, Jitter, RetryPolicy, asset

from lahore_aqi_dagster.logging_utils import log_metrics, log_stage
from lahore_aqi_dagster.resources.pipeline import PipelineConfigResource
from lahore_aqi_dagster.resources.settings import AppSettingsResource
from lahore_aqi_dagster.stages.poll_publish import run_poll_and_publish

API_RETRY = RetryPolicy(
    max_retries=3,
    delay=20,
    backoff=Backoff.EXPONENTIAL,
    jitter=Jitter.PLUS_MINUS,
)


@asset(
    key=AssetKey(["ingestion", "raw_events_published"]),
    group_name="ingestion",
    description=(
        "Poll OpenAQ / Open-Meteo once and publish JSON events to Redpanda. "
        "Retries on temporary API / broker failures."
    ),
    retry_policy=API_RETRY,
)
def raw_events_published(
    context,
    app_settings: AppSettingsResource,
    pipeline_config: PipelineConfigResource,
):
    _ = pipeline_config  # reserved for future poller knobs
    settings = app_settings.get_settings()
    log_stage(
        context,
        "stage_started",
        stage="api_ingestion",
        brokers=settings.redpanda_brokers,
        aq_topic=settings.redpanda_topic_air_quality,
        weather_topic=settings.redpanda_topic_weather,
    )
    result = run_poll_and_publish(settings)
    log_metrics(context, stage="api_ingestion", metrics=result.metrics)
    log_stage(context, "stage_succeeded", stage="api_ingestion")
    context.add_output_metadata(
        {
            "records_published": result.metrics.get("records_published"),
            "failed_polls": result.metrics.get("failed_polls"),
            "brokers": result.brokers,
            "topics": list(result.topics),
        }
    )
    return {
        "metrics": result.metrics,
        "topics": list(result.topics),
    }
