"""Kafka-compatible Redpanda producer for poller ingestion events."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lahore_aqi_poller.events import IngestionEvent
from lahore_aqi_poller.producers.serialization import (
    SCHEMA_NAME,
    SCHEMA_VERSION,
    serialize_event,
)

logger = logging.getLogger(__name__)


class RedpandaPublishError(Exception):
    """Raised when a message cannot be acknowledged by the broker."""


@dataclass(frozen=True, slots=True)
class ProducerHealth:
    """Result of a Redpanda/Kafka producer health probe."""

    healthy: bool
    message: str
    brokers: str | None = None
    topics: tuple[str, ...] | None = None
    details: dict[str, Any] | None = None


class RedpandaPublisher:
    """Reusable producer that publishes :class:`IngestionEvent` JSON to Redpanda.

    Uses the Kafka protocol (``confluent-kafka``) with ``acks=all`` and broker
    idempotence enabled. Message keys are the stable ``event_id`` so partition
    affinity and consumer-side dedupe remain practical.
    """

    def __init__(
        self,
        *,
        brokers: str,
        air_quality_topic: str,
        weather_topic: str,
        client_id: str = "lahore-aqi-poller",
        flush_timeout_seconds: float = 30.0,
        producer_factory: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        if not brokers.strip():
            raise ValueError("brokers must not be empty")
        if not air_quality_topic.strip() or not weather_topic.strip():
            raise ValueError("topic names must not be empty")

        self._brokers = brokers.strip()
        self._air_quality_topic = air_quality_topic.strip()
        self._weather_topic = weather_topic.strip()
        self._flush_timeout_seconds = flush_timeout_seconds
        self._last_delivery_error: str | None = None

        config: dict[str, Any] = {
            "bootstrap.servers": self._brokers,
            "client.id": client_id,
            "acks": "all",
            "enable.idempotence": True,
            "retries": 8,
            "retry.backoff.ms": 250,
            "linger.ms": 5,
            "socket.timeout.ms": 10000,
            # Avoid logging sensitive config if a wrapper dumps the dict.
            "log.connection.close": False,
        }

        factory = producer_factory or _default_producer_factory
        self._producer = factory(config)
        logger.info(
            "redpanda_producer_created",
            extra={
                "brokers": self._brokers,
                "air_quality_topic": self._air_quality_topic,
                "weather_topic": self._weather_topic,
                "schema_name": SCHEMA_NAME,
                "schema_version": SCHEMA_VERSION,
                "acks": "all",
                "enable_idempotence": True,
            },
        )

    @classmethod
    def from_settings(
        cls,
        settings: Any | None = None,
        *,
        producer_factory: Callable[[dict[str, Any]], Any] | None = None,
    ) -> RedpandaPublisher:
        """Build a publisher from application Settings."""
        if settings is None:
            from lahore_air_quality.config import get_settings

            settings = get_settings()
        return cls(
            brokers=settings.redpanda_brokers,
            air_quality_topic=settings.redpanda_topic_air_quality,
            weather_topic=settings.redpanda_topic_weather,
            producer_factory=producer_factory,
        )

    def topic_for(self, event: IngestionEvent) -> str:
        """Route an event to the air-quality or weather topic."""
        if event.record_kind == "air_quality":
            return self._air_quality_topic
        if event.record_kind == "weather":
            return self._weather_topic
        msg = f"unsupported record_kind: {event.record_kind!r}"
        raise ValueError(msg)

    def publish(self, event: IngestionEvent) -> None:
        """Serialize and publish one event; wait for broker acknowledgement."""
        topic = self.topic_for(event)
        payload = serialize_event(event)
        key = event.event_id.encode("utf-8")
        self._last_delivery_error = None

        try:
            self._producer.produce(
                topic=topic,
                key=key,
                value=payload,
                on_delivery=self._on_delivery,
            )
        except BufferError:
            # Local queue full — give the client a chance to drain, then retry once.
            logger.warning(
                "redpanda_local_queue_full",
                extra={"topic": topic, "event_id": event.event_id},
            )
            self._producer.poll(1.0)
            try:
                self._producer.produce(
                    topic=topic,
                    key=key,
                    value=payload,
                    on_delivery=self._on_delivery,
                )
            except Exception as exc:
                logger.exception(
                    "redpanda_publish_failed",
                    extra={
                        "topic": topic,
                        "event_id": event.event_id,
                        "error_type": type(exc).__name__,
                    },
                )
                raise RedpandaPublishError(
                    f"Failed to enqueue event {event.event_id} to {topic}: {type(exc).__name__}"
                ) from exc
        except Exception as exc:
            logger.exception(
                "redpanda_publish_failed",
                extra={
                    "topic": topic,
                    "event_id": event.event_id,
                    "error_type": type(exc).__name__,
                },
            )
            raise RedpandaPublishError(
                f"Failed to enqueue event {event.event_id} to {topic}: {type(exc).__name__}"
            ) from exc

        # Serve delivery callbacks / socket IO.
        self._producer.poll(0)
        remaining = self._producer.flush(self._flush_timeout_seconds)
        if remaining > 0:
            logger.error(
                "redpanda_publish_failed",
                extra={
                    "topic": topic,
                    "event_id": event.event_id,
                    "reason": "flush_timeout",
                    "remaining": remaining,
                },
            )
            raise RedpandaPublishError(
                f"Flush timeout publishing event {event.event_id} to {topic} "
                f"({remaining} message(s) still in queue)"
            )
        if self._last_delivery_error is not None:
            raise RedpandaPublishError(
                f"Broker rejected event {event.event_id} on {topic}: {self._last_delivery_error}"
            )

        logger.info(
            "redpanda_publish_ok",
            extra={
                "topic": topic,
                "event_id": event.event_id,
                "source": event.source,
                "record_kind": event.record_kind,
                "bytes": len(payload),
            },
        )

    def health_check(self) -> ProducerHealth:
        """Probe cluster metadata (no secrets logged)."""
        try:
            metadata = self._producer.list_topics(timeout=10)
            topic_names = tuple(sorted(metadata.topics.keys()))
            expected = {self._air_quality_topic, self._weather_topic}
            missing = sorted(expected - set(topic_names))
            if missing:
                message = f"Redpanda reachable but missing topics: {missing}"
                logger.warning(
                    "redpanda_health_degraded",
                    extra={"missing_topics": missing, "brokers": self._brokers},
                )
                return ProducerHealth(
                    healthy=False,
                    message=message,
                    brokers=self._brokers,
                    topics=topic_names,
                    details={"missing_topics": missing},
                )
            logger.info(
                "redpanda_health_ok",
                extra={"brokers": self._brokers, "topic_count": len(topic_names)},
            )
            return ProducerHealth(
                healthy=True,
                message="Redpanda producer metadata OK",
                brokers=self._brokers,
                topics=topic_names,
            )
        except Exception as exc:
            logger.exception(
                "redpanda_health_failed",
                extra={"brokers": self._brokers, "error_type": type(exc).__name__},
            )
            return ProducerHealth(
                healthy=False,
                message=f"Redpanda health check failed: {type(exc).__name__}",
                brokers=self._brokers,
                details={"error_type": type(exc).__name__},
            )

    def flush(self, timeout: float | None = None) -> None:
        """Flush outstanding messages."""
        self._producer.flush(timeout if timeout is not None else self._flush_timeout_seconds)

    def close(self) -> None:
        """Flush and release producer resources."""
        try:
            self.flush()
        finally:
            # confluent-kafka Producer has no explicit close; dropping refs is enough.
            logger.info("redpanda_producer_closed", extra={"brokers": self._brokers})

    def _on_delivery(self, err: Any, msg: Any) -> None:
        topic = _safe_msg_attr(msg, "topic")
        partition = _safe_msg_attr(msg, "partition")
        if err is not None:
            # Never include broker credentials; error strings from librdkafka are OK.
            self._last_delivery_error = str(err)
            logger.error(
                "redpanda_delivery_failed",
                extra={"error": str(err), "topic": topic, "partition": partition},
            )
            return
        logger.debug(
            "redpanda_delivery_ok",
            extra={
                "topic": topic,
                "partition": partition,
                "offset": _safe_msg_attr(msg, "offset"),
            },
        )


def _default_producer_factory(config: dict[str, Any]) -> Any:
    try:
        from confluent_kafka import Producer
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "confluent-kafka is required for RedpandaPublisher. "
            "Install the poller package dependencies."
        ) from exc
    return Producer(config)


def _safe_msg_attr(msg: Any, name: str) -> Any:
    if msg is None:
        return None
    attr = getattr(msg, name, None)
    if callable(attr):
        try:
            return attr()
        except Exception:  # noqa: BLE001 - best-effort logging only
            return None
    return attr


def wait_for_broker(
    publisher: RedpandaPublisher,
    *,
    attempts: int = 10,
    delay_seconds: float = 1.0,
) -> ProducerHealth:
    """Retry health checks while Redpanda is starting."""
    last = publisher.health_check()
    for _ in range(max(attempts - 1, 0)):
        if last.healthy:
            return last
        time.sleep(delay_seconds)
        last = publisher.health_check()
    return last
