"""Stage 1: external APIs → Redpanda (poller)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lahore_air_quality.config import Settings
from lahore_aqi_dagster.failures import (
    data_validation_failure,
    temporary_api_failure,
)
from lahore_aqi_poller.clients.openaq.exceptions import (
    OpenAQAuthError,
    OpenAQRateLimitError,
    OpenAQTransientError,
)
from lahore_aqi_poller.clients.openmeteo.exceptions import (
    OpenMeteoRateLimitError,
    OpenMeteoTransientError,
)
from lahore_aqi_poller.producers.redpanda import RedpandaPublisher, RedpandaPublishError
from lahore_aqi_poller.service import PollerService


@dataclass(frozen=True, slots=True)
class PollPublishResult:
    metrics: dict[str, Any]
    brokers: str
    topics: tuple[str, str]


def run_poll_and_publish(
    settings: Settings,
    *,
    publisher_factory: Callable[[Settings], Any] | None = None,
    service_factory: Callable[..., PollerService] | None = None,
) -> PollPublishResult:
    """Run one poller cycle and publish to Redpanda.

    Raises Dagster ``Failure`` subclasses via helpers for API / publish issues.
    """
    factory = publisher_factory or RedpandaPublisher.from_settings
    publisher: Any = None
    try:
        publisher = factory(settings)
    except RedpandaPublishError as exc:
        temporary_api_failure(
            f"Redpanda publisher init failed: {type(exc).__name__}",
            stage="api_ingestion",
            error_type=type(exc).__name__,
        )
    except Exception as exc:  # noqa: BLE001
        temporary_api_failure(
            f"Unable to create Redpanda publisher: {type(exc).__name__}",
            stage="api_ingestion",
            error_type=type(exc).__name__,
        )

    health = getattr(publisher, "health_check", lambda: None)()
    if health is not None and hasattr(health, "healthy") and not health.healthy:
        temporary_api_failure(
            f"Redpanda unhealthy: {getattr(health, 'message', 'unknown')}",
            stage="api_ingestion",
            brokers=settings.redpanda_brokers,
        )

    build = service_factory or PollerService.from_settings
    metrics = None
    try:
        service = build(settings, publisher=publisher)
        metrics = service.poll_once()
    except (OpenAQTransientError, OpenMeteoTransientError) as exc:
        temporary_api_failure(
            f"Transient upstream API error: {type(exc).__name__}",
            stage="api_ingestion",
            error_type=type(exc).__name__,
        )
    except (OpenAQRateLimitError, OpenMeteoRateLimitError) as exc:
        temporary_api_failure(
            f"Upstream rate limited: {type(exc).__name__}",
            stage="api_ingestion",
            error_type=type(exc).__name__,
        )
    except OpenAQAuthError as exc:
        data_validation_failure(
            f"OpenAQ authentication failed: {type(exc).__name__}",
            stage="api_ingestion",
            error_type=type(exc).__name__,
        )
    except RedpandaPublishError as exc:
        temporary_api_failure(
            f"Redpanda publish failed: {type(exc).__name__}",
            stage="redpanda_publish",
            error_type=type(exc).__name__,
        )
    finally:
        close = getattr(publisher, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001
                pass

    assert metrics is not None
    metrics_dict = metrics.as_dict()
    if metrics.failed_polls > 0 and metrics.records_published == 0:
        temporary_api_failure(
            "All poll sources failed; nothing published to Redpanda",
            stage="api_ingestion",
            failed_polls=metrics.failed_polls,
            records_published=metrics.records_published,
        )

    return PollPublishResult(
        metrics=metrics_dict,
        brokers=settings.redpanda_brokers,
        topics=(
            settings.redpanda_topic_air_quality,
            settings.redpanda_topic_weather,
        ),
    )
