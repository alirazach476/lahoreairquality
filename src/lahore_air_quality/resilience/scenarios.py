"""Catalog of controlled failure scenarios and expected platform behavior.

This module is the machine-readable companion to ``docs/failure-recovery.md``.
Tests assert against these contracts so portfolio claims stay honest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class ScenarioId(StrEnum):
    OPENAQ_UNAVAILABLE = "openaq_unavailable"
    OPENMETEO_UNAVAILABLE = "openmeteo_unavailable"
    REDPANDA_UNAVAILABLE = "redpanda_unavailable"
    POSTGRES_UNAVAILABLE = "postgres_unavailable"
    OBJECT_STORAGE_UNAVAILABLE = "object_storage_unavailable"
    MALFORMED_EVENT = "malformed_event"
    DUPLICATE_EVENT = "duplicate_event"
    STALE_SENSOR = "stale_sensor"
    MISSING_READINGS = "missing_readings"
    DELAYED_EVENT = "delayed_event"


@dataclass(frozen=True, slots=True)
class FailureScenario:
    """Expected behavior for one controlled failure mode."""

    id: ScenarioId
    title: str
    layer: str
    detect: str
    log_events: tuple[str, ...]
    retry: str
    data_loss_policy: str
    recovery: str
    status_surface: str
    test_module: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["id"] = self.id.value
        payload["log_events"] = list(self.log_events)
        return payload


FAILURE_SCENARIOS: tuple[FailureScenario, ...] = (
    FailureScenario(
        id=ScenarioId.OPENAQ_UNAVAILABLE,
        title="OpenAQ unavailable",
        layer="poller",
        detect="HTTP 5xx/timeout/exhausted retries or missing client → OpenAQError",
        log_events=("poll_failed", "openaq_client_unavailable"),
        retry="Client: up to 3 attempts with backoff (+ Retry-After on 429). "
        "Next poll cycle retries the provider automatically.",
        data_loss_policy="No fabricated AQ rows. Weather polling continues independently.",
        recovery="When OpenAQ returns, the next poll cycle publishes normally.",
        status_surface="PollMetrics.failed_polls / successful_polls; structured poll_failed logs",
        test_module="tests/resilience/test_failure_scenarios.py::test_openaq_unavailable_*",
    ),
    FailureScenario(
        id=ScenarioId.OPENMETEO_UNAVAILABLE,
        title="Open-Meteo unavailable",
        layer="poller",
        detect="HTTP failure / exhausted retries → OpenMeteoError",
        log_events=("poll_failed",),
        retry="Same HTTP retry policy as OpenAQ; next poll cycle retries weather.",
        data_loss_policy="No fabricated weather rows. Air-quality polling continues.",
        recovery="Next successful fetch publishes weather events again.",
        status_surface="PollMetrics per-source counters; poll_failed logs",
        test_module="tests/resilience/test_failure_scenarios.py::test_openmeteo_unavailable_*",
    ),
    FailureScenario(
        id=ScenarioId.REDPANDA_UNAVAILABLE,
        title="Redpanda unavailable",
        layer="poller / consumer",
        detect="Producer health_check unhealthy; publish raises RedpandaPublishError; "
        "consumer kafka_message_error",
        log_events=(
            "redpanda_health_degraded",
            "publish_failed",
            "kafka_message_error",
            "redpanda_delivery_failed",
        ),
        retry="Producer: Kafka retries=8 + idempotent producer. "
        "Failed publishes counted as rejected for that cycle (retried next poll). "
        "Consumer does not commit on broker errors.",
        data_loss_policy="Unpublished poll results are not written to Postgres; "
        "next poll re-fetches. Consumer holds offsets until process succeeds.",
        recovery="When the broker returns, health_check becomes healthy and publish/consume resume.",
        status_surface="ProducerHealth; ConsumerMetrics.failed; pipeline status redpanda component",
        test_module="tests/resilience/test_failure_scenarios.py::test_redpanda_unavailable_*",
    ),
    FailureScenario(
        id=ScenarioId.POSTGRES_UNAVAILABLE,
        title="PostgreSQL unavailable",
        layer="consumer / API",
        detect="PostgresWriteError; check_database_health().healthy is False; GET /health → 503",
        log_events=("postgres_write_failed", "processing_failed", "offset_not_committed"),
        retry="Consumer: exponential backoff (2s→60s), Kafka offset NOT committed; "
        "S3 object retained for idempotent replay.",
        data_loss_policy="No silent drop — message stays on the topic until PG accepts the write.",
        recovery="When Postgres returns, redelivery writes observation (ON CONFLICT safe) and commits.",
        status_surface="GET /health database=down; ComponentStatus postgres; ProcessResult.failed_stage=postgres",
        test_module="tests/resilience/test_failure_scenarios.py::test_postgres_unavailable_*",
    ),
    FailureScenario(
        id=ScenarioId.OBJECT_STORAGE_UNAVAILABLE,
        title="Object storage unavailable",
        layer="consumer",
        detect="ObjectStoreError on put_json / exists",
        log_events=("processing_failed", "offset_not_committed"),
        retry="Same consumer backoff as Postgres; PostgreSQL is not attempted until S3 succeeds.",
        data_loss_policy="S3-before-PG ordering prevents warehouse rows without a raw archive.",
        recovery="When MinIO returns, put succeeds (deterministic key) then PG write; offset commits.",
        status_surface="ProcessResult.failed_stage=s3; ConsumerMetrics.failed",
        test_module="tests/resilience/test_failure_scenarios.py::test_object_storage_unavailable_*",
    ),
    FailureScenario(
        id=ScenarioId.MALFORMED_EVENT,
        title="Malformed event",
        layer="consumer / poller",
        detect="EventValidationError on envelope; PermanentPostgresWriteError on normalized shape; "
        "poller transform returns None",
        log_events=("event_rejected",),
        retry="None (non-retryable). Offset is committed to avoid poison-pill loops.",
        data_loss_policy="Invalid payloads are never written as observations. "
        "If S3 already archived a bad normalized shape, the object is retained for audit.",
        recovery="N/A for the bad message; subsequent valid messages process normally.",
        status_surface="ProcessResult.status=rejected; PollMetrics.records_rejected; ConsumerMetrics.rejected",
        test_module="tests/resilience/test_failure_scenarios.py::test_malformed_event_*",
    ),
    FailureScenario(
        id=ScenarioId.DUPLICATE_EVENT,
        title="Duplicate event",
        layer="consumer / warehouse",
        detect="Stable event_id; PostgreSQL ON CONFLICT DO NOTHING; S3 key already exists",
        log_events=("processing_ok", "postgres_write_ok"),
        retry="N/A — duplicates are acknowledged as success-like (commit offset).",
        data_loss_policy="Exactly-once *effect*: second delivery does not create a second row.",
        recovery="Pipeline continues; metrics.duplicate increments for operators.",
        status_surface="ProcessResult.status=duplicate; InsertResult reasons duplicate_*",
        test_module="tests/resilience/test_failure_scenarios.py::test_duplicate_event_*",
    ),
    FailureScenario(
        id=ScenarioId.STALE_SENSOR,
        title="Stale sensor",
        layer="data quality / API",
        detect="is_stale(latest_observed_at); inactive_stations; API freshness.is_fresh",
        log_events=("data_quality report freshness.stale",),
        retry="N/A — observational. Ingestion still accepts late-but-valid readings.",
        data_loss_policy="Stale sensors are flagged, never deleted or zero-filled.",
        recovery="When new observations arrive, freshness clears on the next quality report / API read.",
        status_surface="DataQualityReport.freshness; API current AQI freshness fields",
        test_module="tests/resilience/test_failure_scenarios.py::test_stale_sensor_*",
    ),
    FailureScenario(
        id=ScenarioId.MISSING_READINGS,
        title="Missing readings",
        layer="poller / quality",
        detect="poll_empty_result; rule_missing_value / rule_missing_timestamp; find_missing_intervals",
        log_events=("poll_empty_result", "rule findings missing_value / missing_timestamp"),
        retry="Next poll cycle re-queries providers. Gaps are reported, not imputed.",
        data_loss_policy="Never invent zeros or interpolate concentrations for gaps.",
        recovery="When data resumes, gaps remain visible historically; new points classify normally.",
        status_surface="DataQualityReport.missing_intervals / null_counts; PollMetrics empty polls",
        test_module="tests/resilience/test_failure_scenarios.py::test_missing_readings_*",
    ),
    FailureScenario(
        id=ScenarioId.DELAYED_EVENT,
        title="Delayed event",
        layer="quality",
        detect="ingested_at − observed_at > DELAYED_INGEST_AFTER (default 6h) → delayed_ingest",
        log_events=("classification finding delayed_ingest",),
        retry="N/A — event is accepted and stored; delay is surfaced as suspect.",
        data_loss_policy="Late events are kept (backfill-friendly). Not dropped for being late.",
        recovery="Operators see delayed_ingest_count / max_ingest_delay_hours on the quality report.",
        status_surface="RuleFinding delayed_ingest; report freshness.delayed_ingest_*",
        test_module="tests/resilience/test_failure_scenarios.py::test_delayed_event_*",
    ),
)


def list_scenarios() -> list[FailureScenario]:
    return list(FAILURE_SCENARIOS)


def get_scenario(scenario_id: ScenarioId | str) -> FailureScenario:
    key = ScenarioId(scenario_id) if not isinstance(scenario_id, ScenarioId) else scenario_id
    for scenario in FAILURE_SCENARIOS:
        if scenario.id is key:
            return scenario
    raise KeyError(f"Unknown failure scenario: {scenario_id}")
