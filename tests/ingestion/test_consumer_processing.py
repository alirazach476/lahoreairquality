"""Unit tests for consumer processing logic (mocked S3 + PostgreSQL)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from lahore_air_quality.db.repository import InsertResult
from lahore_aqi_consumer.processing import EventProcessor
from lahore_aqi_consumer.schema import deserialize_event
from lahore_aqi_consumer.service import ConsumerService
from lahore_aqi_consumer.storage.postgres import (
    PostgresObservationWriter,
    PostgresWriteError,
    PostgresWriteResult,
)
from lahore_aqi_consumer.storage.s3 import (
    ObjectPutResult,
    ObjectStoreError,
    build_raw_object_key,
)


def _envelope(
    *,
    event_id: str = "openaq:501:abc",
    kind: str = "air_quality",
    source: str = "openaq",
) -> dict[str, Any]:
    if kind == "air_quality":
        normalized = {
            "station_id": "9001",
            "pollutant": "pm25",
            "value": "42.5",
            "unit": "µg/m³",
            "observed_at": "2026-10-24T05:00:00+00:00",
            "source": "openaq",
            "raw_record_id": event_id,
        }
    else:
        normalized = {
            "latitude": "31.520400",
            "longitude": "74.358700",
            "temperature_c": "28.5",
            "observed_at": "2026-10-24T05:00:00+00:00",
            "source": "open-meteo",
            "raw_record_id": event_id,
        }
        source = "open-meteo"
    return {
        "schema": {"name": "lahore_aqi.ingestion_event", "version": "1.0.0"},
        "event_id": event_id,
        "idempotency_key": event_id,
        "source": source,
        "record_kind": kind,
        "event_timestamp": "2026-10-24T05:00:00+00:00",
        "ingested_at": "2026-10-24T06:00:00+00:00",
        "normalized": normalized,
        "raw": {"original": True, "value": 42.5},
    }


class _FakeStore:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self.fail = False

    def exists(self, *, key: str) -> bool:
        return key in self.objects

    def put_json(self, *, key: str, document: dict[str, Any]) -> ObjectPutResult:
        if self.fail:
            raise ObjectStoreError("s3 unavailable")
        existed = key in self.objects
        self.objects[key] = document
        return ObjectPutResult(bucket="test", key=key, already_existed=existed)


def _pg_writer(
    *,
    duplicate: bool = False,
    fail: bool = False,
) -> PostgresObservationWriter:
    writer = MagicMock(spec=PostgresObservationWriter)
    if fail:
        writer.write.side_effect = PostgresWriteError("db down")
    elif duplicate:
        writer.write.return_value = PostgresWriteResult(
            payload=InsertResult(False, "duplicate_raw_record"),
            observation=InsertResult(False, "duplicate_observation"),
        )
    else:
        writer.write.return_value = PostgresWriteResult(
            payload=InsertResult(True, "inserted"),
            observation=InsertResult(True, "inserted"),
        )
    return writer


def test_deserialize_valid_and_invalid() -> None:
    env = deserialize_event(_envelope())
    assert env.event_id == "openaq:501:abc"
    assert env.schema_meta.version == "1.0.0"

    with pytest.raises(Exception):
        deserialize_event(b"not-json")


def test_deterministic_object_key() -> None:
    ts = datetime(2026, 10, 24, 5, 0, tzinfo=UTC)
    key1 = build_raw_object_key(
        record_kind="air_quality",
        source="openaq",
        event_id="openaq:501:abc",
        event_timestamp=ts,
    )
    key2 = build_raw_object_key(
        record_kind="air_quality",
        source="openaq",
        event_id="openaq:501:abc",
        event_timestamp=ts,
    )
    assert key1 == key2
    assert key1 == "raw/air_quality/openaq/2026/10/24/openaq_501_abc.json"


def test_successful_process_stores_s3_and_postgres() -> None:
    store = _FakeStore()
    pg = _pg_writer()
    processor = EventProcessor(object_store=store, postgres_writer=pg)
    payload = _envelope()
    result = processor.process(json.dumps(payload).encode("utf-8"))

    assert result.status == "processed"
    assert result.s3_ok and result.postgres_ok
    assert result.s3_key in store.objects
    # Original JSON preserved (not only normalized).
    assert store.objects[result.s3_key]["raw"]["original"] is True
    pg.write.assert_called_once()


def test_malformed_event_rejected_without_crash() -> None:
    store = _FakeStore()
    pg = _pg_writer()
    processor = EventProcessor(object_store=store, postgres_writer=pg)
    result = processor.process(b'{"not": "valid schema"}')
    assert result.status == "rejected"
    assert result.failed_stage == "validate"
    assert store.objects == {}
    pg.write.assert_not_called()


def test_s3_failure_does_not_touch_postgres_and_is_failed() -> None:
    store = _FakeStore()
    store.fail = True
    pg = _pg_writer()
    processor = EventProcessor(object_store=store, postgres_writer=pg)
    result = processor.process(_envelope())
    assert result.status == "failed"
    assert result.failed_stage == "s3"
    assert result.s3_ok is False
    pg.write.assert_not_called()


def test_postgres_failure_after_s3_is_visible_and_failed() -> None:
    store = _FakeStore()
    pg = _pg_writer(fail=True)
    processor = EventProcessor(object_store=store, postgres_writer=pg)
    result = processor.process(_envelope())
    assert result.status == "failed"
    assert result.failed_stage == "postgres"
    assert result.s3_ok is True
    assert result.postgres_ok is False
    assert result.s3_key in store.objects


def test_duplicate_kafka_message_is_idempotent() -> None:
    store = _FakeStore()
    pg = _pg_writer()
    processor = EventProcessor(object_store=store, postgres_writer=pg)
    first = processor.process(_envelope())
    assert first.status == "processed"

    pg_dup = _pg_writer(duplicate=True)
    processor2 = EventProcessor(object_store=store, postgres_writer=pg_dup)
    second = processor2.process(_envelope())
    assert second.status == "duplicate"
    assert len(store.objects) == 1


def test_consumer_commits_only_on_success_not_on_failure() -> None:
    store = _FakeStore()
    processor = EventProcessor(object_store=store, postgres_writer=_pg_writer())

    commits: list[Any] = []

    class FakeMsg:
        def __init__(self, value: bytes, topic: str = "aq.raw") -> None:
            self._value = value
            self._topic = topic

        def error(self) -> None:
            return None

        def value(self) -> bytes:
            return self._value

        def topic(self) -> str:
            return self._topic

        def partition(self) -> int:
            return 0

        def offset(self) -> int:
            return 10

    class FakeConsumer:
        def __init__(self) -> None:
            self._queue = [
                FakeMsg(json.dumps(_envelope()).encode("utf-8")),
            ]
            self.closed = False

        def subscribe(self, _topics: list[str]) -> None:
            return None

        def poll(self, _timeout: float) -> FakeMsg | None:
            if self._queue:
                return self._queue.pop(0)
            return None

        def commit(self, message: Any = None, asynchronous: bool = False) -> None:
            commits.append(message)

        def close(self) -> None:
            self.closed = True

    consumer = FakeConsumer()
    service = ConsumerService(
        processor=processor,
        consumer=consumer,
        topics=["aq.raw", "weather.raw"],
        poll_timeout_seconds=0.01,
        retry_backoff_seconds=0.01,
    )
    service.run(max_messages=1)
    assert len(commits) == 1
    assert service.metrics.processed == 1
    assert consumer.closed is True

    # Failure path: no commit
    store2 = _FakeStore()
    store2.fail = True
    processor_fail = EventProcessor(object_store=store2, postgres_writer=_pg_writer())
    commits.clear()
    consumer2 = FakeConsumer()
    consumer2._queue = [FakeMsg(json.dumps(_envelope()).encode("utf-8"))]
    service2 = ConsumerService(
        processor=processor_fail,
        consumer=consumer2,
        topics=["aq.raw"],
        poll_timeout_seconds=0.01,
        retry_backoff_seconds=0.01,
        max_retry_backoff_seconds=0.01,
    )
    service2.run(max_messages=1)
    assert commits == []
    assert service2.metrics.failed == 1


def test_graceful_shutdown_stops_loop() -> None:
    store = _FakeStore()
    processor = EventProcessor(object_store=store, postgres_writer=_pg_writer())

    class BlockingConsumer:
        def subscribe(self, _topics: list[str]) -> None:
            return None

        def poll(self, _timeout: float) -> None:
            return None

        def close(self) -> None:
            return None

        def commit(self, **_kwargs: Any) -> None:
            return None

    service = ConsumerService(
        processor=processor,
        consumer=BlockingConsumer(),
        topics=["aq.raw"],
        poll_timeout_seconds=0.05,
    )
    import threading

    thread = threading.Thread(target=lambda: service.run(), daemon=True)
    thread.start()
    threading.Event().wait(0.1)
    service.request_shutdown()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
