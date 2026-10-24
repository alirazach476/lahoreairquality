"""Unit tests for the Redpanda producer (mocked Kafka client; no broker required)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from lahore_aqi_poller.events import IngestionEvent
from lahore_aqi_poller.producers.redpanda import (
    RedpandaPublisher,
    RedpandaPublishError,
)
from lahore_aqi_poller.producers.serialization import (
    SCHEMA_NAME,
    SCHEMA_VERSION,
    build_event_envelope,
    serialize_event,
)


def _event(*, kind: str = "air_quality", event_id: str = "openaq:1:abc") -> IngestionEvent:
    source = "openaq" if kind == "air_quality" else "open-meteo"
    return IngestionEvent(
        event_id=event_id,
        idempotency_key=event_id,
        source=source,  # type: ignore[arg-type]
        record_kind=kind,  # type: ignore[arg-type]
        ingested_at=datetime(2026, 10, 24, 6, 0, tzinfo=UTC),
        observed_at=datetime(2026, 10, 24, 5, 0, tzinfo=UTC),
        normalized={"pollutant": "pm25", "value": 42.5},
        raw={"value": 42.5},
    )


class _FakeMessage:
    def __init__(self, topic: str, partition: int = 0, offset: int = 1) -> None:
        self._topic = topic
        self._partition = partition
        self._offset = offset

    def topic(self) -> str:
        return self._topic

    def partition(self) -> int:
        return self._partition

    def offset(self) -> int:
        return self._offset


class _FakeProducer:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.produced: list[dict[str, Any]] = []
        self._delivery_err: Exception | None = None
        self.flush_remaining = 0
        self.topics = {"aq.raw": object(), "weather.raw": object()}

    def produce(
        self,
        *,
        topic: str,
        key: bytes,
        value: bytes,
        on_delivery: Any,
    ) -> None:
        self.produced.append(
            {"topic": topic, "key": key, "value": value, "on_delivery": on_delivery}
        )
        on_delivery(self._delivery_err, _FakeMessage(topic))

    def poll(self, _timeout: float) -> int:
        return 0

    def flush(self, _timeout: float) -> int:
        return self.flush_remaining

    def list_topics(self, timeout: float = 10) -> Any:  # noqa: ARG002
        meta = MagicMock()
        meta.topics = dict(self.topics)
        return meta


def _publisher(fake: _FakeProducer | None = None) -> tuple[RedpandaPublisher, _FakeProducer]:
    producer = fake or _FakeProducer({})

    def factory(config: dict[str, Any]) -> _FakeProducer:
        producer.config = config
        return producer

    pub = RedpandaPublisher(
        brokers="localhost:19092",
        air_quality_topic="aq.raw",
        weather_topic="weather.raw",
        producer_factory=factory,
    )
    return pub, producer


def test_serialize_event_includes_required_envelope_fields() -> None:
    event = _event()
    envelope = build_event_envelope(event)
    assert envelope["schema"]["name"] == SCHEMA_NAME
    assert envelope["schema"]["version"] == SCHEMA_VERSION
    assert envelope["event_id"] == "openaq:1:abc"
    assert envelope["source"] == "openaq"
    assert envelope["event_timestamp"] == "2026-10-24T05:00:00+00:00"
    assert envelope["ingested_at"] == "2026-10-24T06:00:00+00:00"
    assert envelope["normalized"]["pollutant"] == "pm25"
    assert envelope["raw"]["value"] == 42.5

    raw = serialize_event(event)
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["event_id"] == envelope["event_id"]


def test_publish_routes_topics_and_uses_event_id_as_key() -> None:
    pub, producer = _publisher()
    assert producer.config["acks"] == "all"
    assert producer.config["enable.idempotence"] is True
    assert "sasl.password" not in producer.config

    pub.publish(_event(kind="air_quality", event_id="aq-1"))
    pub.publish(_event(kind="weather", event_id="wx-1"))

    assert producer.produced[0]["topic"] == "aq.raw"
    assert producer.produced[0]["key"] == b"aq-1"
    assert producer.produced[1]["topic"] == "weather.raw"
    assert producer.produced[1]["key"] == b"wx-1"

    body = json.loads(producer.produced[0]["value"].decode("utf-8"))
    assert body["schema"]["version"] == SCHEMA_VERSION
    assert body["event_id"] == "aq-1"


def test_publish_raises_on_delivery_failure() -> None:
    fake = _FakeProducer({})
    fake._delivery_err = RuntimeError("broker down")
    pub, _ = _publisher(fake)

    with pytest.raises(RedpandaPublishError, match="broker down"):
        pub.publish(_event())


def test_publish_raises_on_flush_timeout() -> None:
    fake = _FakeProducer({})
    fake.flush_remaining = 1
    pub, _ = _publisher(fake)

    with pytest.raises(RedpandaPublishError, match="Flush timeout"):
        pub.publish(_event())


def test_health_check_healthy_and_missing_topics() -> None:
    pub, fake = _publisher()
    healthy = pub.health_check()
    assert healthy.healthy is True
    assert healthy.brokers == "localhost:19092"
    assert "aq.raw" in (healthy.topics or ())

    fake.topics = {"aq.raw": object()}  # weather missing
    degraded = pub.health_check()
    assert degraded.healthy is False
    assert degraded.details is not None
    assert "weather.raw" in degraded.details["missing_topics"]


def test_health_check_broker_failure() -> None:
    fake = _FakeProducer({})

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("connection refused")

    fake.list_topics = boom  # type: ignore[method-assign]
    pub, _ = _publisher(fake)
    result = pub.health_check()
    assert result.healthy is False
    assert "OSError" in result.message


def test_idempotent_key_stable_across_publishes() -> None:
    pub, producer = _publisher()
    event = _event(event_id="stable-key")
    pub.publish(event)
    pub.publish(event)
    assert producer.produced[0]["key"] == producer.produced[1]["key"] == b"stable-key"
