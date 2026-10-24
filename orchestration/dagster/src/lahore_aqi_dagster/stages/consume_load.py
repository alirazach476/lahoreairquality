"""Stage 2–3: Redpanda → S3 + PostgreSQL (bounded consumer drain)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lahore_air_quality.config import Settings
from lahore_air_quality.db.health import check_database_health
from lahore_air_quality.db.session import dispose_engine, get_session_factory
from lahore_aqi_consumer.processing import EventProcessor
from lahore_aqi_consumer.service import ConsumerService
from lahore_aqi_consumer.storage.postgres import (
    PostgresObservationWriter,
    PostgresWriteError,
)
from lahore_aqi_consumer.storage.s3 import ObjectStoreError, S3ObjectStore
from lahore_aqi_dagster.failures import (
    database_failure,
    temporary_api_failure,
)


@dataclass(frozen=True, slots=True)
class ConsumeLoadResult:
    metrics: dict[str, Any]
    messages_handled: int
    max_messages: int


def run_consume_and_load(
    settings: Settings,
    *,
    max_messages: int = 200,
    idle_polls_before_stop: int = 5,
    poll_timeout_seconds: float = 1.0,
    store_factory: Callable[[Settings], S3ObjectStore] | None = None,
    consumer_factory: Callable[[], ConsumerService] | None = None,
) -> ConsumeLoadResult:
    """Drain up to ``max_messages`` from Redpanda into S3 + Postgres.

    Stops early after ``idle_polls_before_stop`` consecutive empty polls so the
    Dagster asset completes when the topic is caught up.
    """
    dispose_engine()
    health = check_database_health()
    if not health.healthy:
        database_failure(
            health.message,
            stage="database",
            error_type=(health.details or {}).get("error_type", "unknown"),
        )

    build_store = store_factory or S3ObjectStore.from_settings
    try:
        store = build_store(settings)
        store.ensure_bucket()
    except ObjectStoreError as exc:
        temporary_api_failure(
            f"Object storage unavailable: {type(exc).__name__}",
            stage="object_storage",
            error_type=type(exc).__name__,
            bucket=settings.s3_bucket,
        )
    except Exception as exc:  # noqa: BLE001
        temporary_api_failure(
            f"Object storage init failed: {type(exc).__name__}",
            stage="object_storage",
            error_type=type(exc).__name__,
        )

    processor = EventProcessor(
        object_store=store,
        postgres_writer=PostgresObservationWriter(get_session_factory()),
    )

    def _default_consumer() -> ConsumerService:
        return ConsumerService.from_settings(settings, processor=processor)

    build_consumer = consumer_factory or _default_consumer
    try:
        service = build_consumer()
    except Exception as exc:  # noqa: BLE001
        temporary_api_failure(
            f"Redpanda consumer init failed: {type(exc).__name__}",
            stage="redpanda_consume",
            error_type=type(exc).__name__,
        )

    service._consumer.subscribe(service._topics)  # noqa: SLF001
    handled = 0
    idle = 0
    try:
        while handled < max_messages and idle < idle_polls_before_stop:
            msg = service._consumer.poll(poll_timeout_seconds)  # noqa: SLF001
            if msg is None:
                idle += 1
                continue
            if msg.error():
                temporary_api_failure(
                    f"Kafka message error: {msg.error()}",
                    stage="redpanda_consume",
                )
            idle = 0
            try:
                service._handle_message(msg)  # noqa: SLF001
            except PostgresWriteError as exc:
                database_failure(
                    f"PostgreSQL write failed: {type(exc).__name__}",
                    stage="database",
                    error_type=type(exc).__name__,
                )
            except ObjectStoreError as exc:
                temporary_api_failure(
                    f"S3 write failed: {type(exc).__name__}",
                    stage="object_storage",
                    error_type=type(exc).__name__,
                )
            handled += 1
    finally:
        service._close()  # noqa: SLF001
        dispose_engine()

    metrics = service.metrics.as_dict()
    if service.metrics.failed > 0 and service.metrics.processed == 0 and handled > 0:
        database_failure(
            "Consumer processed messages but all sink writes failed",
            stage="database",
            failed=service.metrics.failed,
            consumed=service.metrics.consumed,
        )

    return ConsumeLoadResult(
        metrics=metrics,
        messages_handled=handled,
        max_messages=max_messages,
    )
