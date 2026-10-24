"""Redpanda consumer loop: poll → process → commit (on success only)."""

from __future__ import annotations

import logging
import signal
import threading
import time
from collections.abc import Callable
from types import FrameType
from typing import Any

from lahore_aqi_consumer.metrics import ConsumerMetrics
from lahore_aqi_consumer.processing import EventProcessor, ProcessResult

logger = logging.getLogger(__name__)


class ConsumerService:
    """Consume air-quality and weather topics with manual offset commits."""

    def __init__(
        self,
        *,
        processor: EventProcessor,
        consumer: Any,
        topics: list[str],
        metrics: ConsumerMetrics | None = None,
        poll_timeout_seconds: float = 1.0,
        retry_backoff_seconds: float = 2.0,
        max_retry_backoff_seconds: float = 60.0,
    ) -> None:
        self._processor = processor
        self._consumer = consumer
        self._topics = topics
        self.metrics = metrics or ConsumerMetrics()
        self._poll_timeout_seconds = poll_timeout_seconds
        self._retry_backoff_seconds = retry_backoff_seconds
        self._max_retry_backoff_seconds = max_retry_backoff_seconds
        self._stop = threading.Event()
        self._failure_backoff = retry_backoff_seconds

    @classmethod
    def from_settings(
        cls,
        settings: Any | None = None,
        *,
        processor: EventProcessor,
        consumer_factory: Callable[[dict[str, Any]], Any] | None = None,
    ) -> ConsumerService:
        if settings is None:
            from lahore_air_quality.config import get_settings

            settings = get_settings()

        config = {
            "bootstrap.servers": settings.redpanda_brokers,
            "group.id": settings.redpanda_consumer_group,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
            "client.id": "lahore-aqi-consumer",
        }
        factory = consumer_factory or _default_consumer_factory
        consumer = factory(config)
        topics = [
            settings.redpanda_topic_air_quality,
            settings.redpanda_topic_weather,
        ]
        return cls(processor=processor, consumer=consumer, topics=topics)

    def request_shutdown(self, *_args: object) -> None:
        logger.info("shutdown_requested")
        self._stop.set()

    def install_signal_handlers(self) -> None:
        def _handler(signum: int, _frame: FrameType | None) -> None:
            logger.info("signal_received", extra={"signum": signum})
            self.request_shutdown()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                logger.debug("signal_handler_not_installed", extra={"signum": int(sig)})

    def run(self, *, max_messages: int | None = None) -> ConsumerMetrics:
        """Run until shutdown. Optionally stop after ``max_messages`` consumed."""
        self.install_signal_handlers()
        self._consumer.subscribe(self._topics)
        logger.info(
            "consumer_started",
            extra={
                "topics": self._topics,
                "max_messages": max_messages,
            },
        )

        handled = 0
        try:
            while not self._stop.is_set():
                if max_messages is not None and handled >= max_messages:
                    break
                msg = self._consumer.poll(self._poll_timeout_seconds)
                if msg is None:
                    continue
                if msg.error():
                    # Don't commit; surface and continue polling.
                    logger.error(
                        "kafka_message_error",
                        extra={"error": str(msg.error())},
                    )
                    self.metrics.mark_failed("unknown")
                    # Count toward max_messages so finite runs (tests/jobs) terminate.
                    handled += 1
                    continue

                self._handle_message(msg)
                handled += 1
        finally:
            self._close()
            logger.info("consumer_stopped", extra={"metrics": self.metrics.as_dict()})
        return self.metrics

    def process_raw(self, payload: bytes | str | dict[str, Any]) -> ProcessResult:
        """Process a payload without Kafka (unit tests / replay tools)."""
        return self._apply_result(self._processor.process(payload), commit=None)

    def _handle_message(self, msg: Any) -> None:
        topic = msg.topic()
        payload = msg.value() or b""
        source_hint = _source_hint_from_topic(topic)
        self.metrics.mark_consumed(source_hint)

        result = self._processor.process(payload)
        self._apply_result(
            result,
            commit=lambda: self._commit(msg),
            topic=topic,
            partition=msg.partition(),
            offset=msg.offset(),
        )

    def _apply_result(
        self,
        result: ProcessResult,
        *,
        commit: Callable[[], None] | None,
        topic: str | None = None,
        partition: int | None = None,
        offset: int | None = None,
    ) -> ProcessResult:
        source = result.source or "unknown"

        if result.status == "rejected":
            self.metrics.mark_rejected(source)
            # Non-retryable: commit to avoid poison-pill infinite loop (logged).
            if commit is not None:
                commit()
            self._failure_backoff = self._retry_backoff_seconds
            return result

        if result.status == "failed":
            self.metrics.mark_failed(source)
            logger.error(
                "offset_not_committed",
                extra={
                    "event_id": result.event_id,
                    "failed_stage": result.failed_stage,
                    "s3_ok": result.s3_ok,
                    "postgres_ok": result.postgres_ok,
                    "s3_key": result.s3_key,
                    "topic": topic,
                    "partition": partition,
                    "offset": offset,
                },
            )
            time.sleep(self._failure_backoff)
            self._failure_backoff = min(self._failure_backoff * 2, self._max_retry_backoff_seconds)
            return result

        if result.status == "duplicate":
            self.metrics.mark_duplicate(source)
        else:
            self.metrics.mark_processed(source)

        if commit is not None:
            commit()
        self._failure_backoff = self._retry_backoff_seconds
        return result

    def _commit(self, msg: Any) -> None:
        try:
            self._consumer.commit(message=msg, asynchronous=False)
            logger.debug(
                "offset_committed",
                extra={
                    "topic": msg.topic(),
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                },
            )
        except Exception:
            logger.exception(
                "offset_commit_failed",
                extra={
                    "topic": msg.topic(),
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                },
            )
            # Treat as failure path — message may be redelivered.
            raise

    def _close(self) -> None:
        try:
            self._consumer.close()
        except Exception:
            logger.exception("consumer_close_failed")


def _default_consumer_factory(config: dict[str, Any]) -> Any:
    try:
        from confluent_kafka import Consumer
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "confluent-kafka is required for ConsumerService. "
            "Install the consumer package dependencies."
        ) from exc
    return Consumer(config)


def _source_hint_from_topic(topic: str | None) -> str:
    if not topic:
        return "unknown"
    if "weather" in topic:
        return "open-meteo"
    if "aq" in topic or "air" in topic:
        return "openaq"
    return "unknown"
