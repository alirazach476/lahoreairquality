"""End-to-end smoke test: mocked APIs → poller → Redpanda → consumer → PG + S3.

Does **not** call live OpenAQ or Open-Meteo. Requires local Postgres, MinIO, and
Redpanda (started by ``python scripts/run_smoke_test.py`` / ``make smoke``).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from lahore_air_quality.db.models import (
    AirQualityObservation,
    IngestionPayload,
    WeatherObservation,
)
from lahore_air_quality.db.session import get_session_factory
from lahore_aqi_consumer.processing import EventProcessor
from lahore_aqi_consumer.service import ConsumerService
from lahore_aqi_consumer.storage.postgres import PostgresObservationWriter
from lahore_aqi_consumer.storage.s3 import S3ObjectStore, build_raw_object_key
from lahore_aqi_poller.clients.openaq import OpenAQClient
from lahore_aqi_poller.clients.openmeteo import OpenMeteoClient
from lahore_aqi_poller.events import IngestionEvent
from lahore_aqi_poller.producers import RecordingPublisher
from lahore_aqi_poller.producers.redpanda import RedpandaPublisher, wait_for_broker
from lahore_aqi_poller.service import PollerService
from tests.ingestion.fixtures.openaq_payloads import (
    latest_success_response,
    locations_success_response,
)
from tests.ingestion.fixtures.openmeteo_payloads import forecast_success_response

pytestmark = pytest.mark.smoke

logger = logging.getLogger(__name__)


class _TeePublisher:
    """Publish to Redpanda while retaining the exact events for assertions."""

    def __init__(self, inner: RedpandaPublisher, recorder: RecordingPublisher) -> None:
        self._inner = inner
        self._recorder = recorder

    def publish(self, event: IngestionEvent) -> None:
        self._recorder.publish(event)
        self._inner.publish(event)

    def close(self) -> None:
        self._inner.close()


def _smoke_openaq_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v3/locations":
        return httpx.Response(200, json=locations_success_response())
    if request.url.path == "/v3/locations/9001/latest":
        return httpx.Response(200, json=latest_success_response())
    return httpx.Response(404, json={"detail": f"unexpected path {request.url.path}"})


def _smoke_openmeteo_handler(request: httpx.Request) -> httpx.Response:
    if "/v1/forecast" in request.url.path:
        return httpx.Response(200, json=forecast_success_response())
    return httpx.Response(404, json={"detail": f"unexpected path {request.url.path}"})


def _build_mocked_clients() -> tuple[OpenAQClient, OpenMeteoClient]:
    openaq = OpenAQClient(
        api_key="smoke-test-key-not-real",
        base_url="https://api.openaq.org",
        transport=httpx.MockTransport(_smoke_openaq_handler),
        min_request_interval_seconds=0.0,
        max_retries=1,
    )
    openmeteo = OpenMeteoClient(
        latitude=31.5204,
        longitude=74.3587,
        forecast_base_url="https://api.open-meteo.com",
        archive_base_url="https://archive-api.open-meteo.com",
        transport=httpx.MockTransport(_smoke_openmeteo_handler),
        max_retries=1,
    )
    return openaq, openmeteo


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _run_consumer(
    *,
    brokers: str,
    topics: list[str],
    group_id: str,
    store: S3ObjectStore,
    max_messages: int,
    timeout_seconds: float = 60.0,
) -> ConsumerService:
    """Consume up to ``max_messages`` with a hard deadline (smoke must not hang)."""
    from confluent_kafka import Consumer

    processor = EventProcessor(
        object_store=store,
        postgres_writer=PostgresObservationWriter(get_session_factory()),
    )
    consumer = Consumer(
        {
            "bootstrap.servers": brokers,
            "group.id": group_id,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
            "client.id": "lahore-aqi-smoke-consumer",
        }
    )
    service = ConsumerService(
        processor=processor,
        consumer=consumer,
        topics=topics,
        poll_timeout_seconds=0.5,
        retry_backoff_seconds=0.2,
        max_retry_backoff_seconds=2.0,
    )

    deadline = time.monotonic() + timeout_seconds
    service._consumer.subscribe(topics)  # noqa: SLF001
    handled = 0
    try:
        while handled < max_messages and time.monotonic() < deadline:
            msg = service._consumer.poll(0.5)  # noqa: SLF001
            if msg is None:
                continue
            if msg.error():
                logger.error("smoke_kafka_error", extra={"error": str(msg.error())})
                service.metrics.mark_failed("unknown")
                continue
            service._handle_message(msg)  # noqa: SLF001
            handled += 1
    finally:
        service._close()  # noqa: SLF001

    assert handled == max_messages, (
        f"smoke consumer timed out: got {handled}/{max_messages} "
        f"in {timeout_seconds}s (metrics={service.metrics.as_dict()})"
    )
    return service


def _s3_get_json(store: S3ObjectStore, key: str) -> dict[str, Any]:
    response = store._client.get_object(Bucket=store._bucket, Key=key)  # noqa: SLF001
    body = response["Body"].read()
    return json.loads(body.decode("utf-8"))


def test_ingestion_pipeline_end_to_end(
    smoke_settings,
    smoke_engine: Engine,
    smoke_schema: None,
    smoke_minio: S3ObjectStore,
    smoke_brokers: str,
    smoke_topics: tuple[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify the full mocked-API → Redpanda → sinks path, including dupes/rejects."""
    aq_topic, wx_topic = smoke_topics
    run_id = uuid.uuid4().hex[:8]
    group_a = f"lahore-aqi-smoke-{run_id}-a"
    group_b = f"lahore-aqi-smoke-{run_id}-b"
    group_c = f"lahore-aqi-smoke-{run_id}-c"

    caplog.set_level(logging.INFO)

    openaq, openmeteo = _build_mocked_clients()
    redpanda = RedpandaPublisher(
        brokers=smoke_brokers,
        air_quality_topic=aq_topic,
        weather_topic=wx_topic,
        client_id=f"lahore-aqi-smoke-poller-{run_id}",
    )
    health = wait_for_broker(redpanda, attempts=15, delay_seconds=1.0)
    assert health.healthy, health.message

    recorder = RecordingPublisher()
    publisher = _TeePublisher(redpanda, recorder)
    poller = PollerService(
        openaq_client=openaq,
        openmeteo_client=openmeteo,
        publisher=publisher,
        interval_seconds=60.0,
        enable_openaq=True,
        enable_openmeteo=True,
    )

    # --- 1–3: clients → poller → publish ---
    poll_metrics = poller.poll_once()
    publisher.close()
    openaq.close()
    openmeteo.close()

    assert poll_metrics.records_published >= 2, poll_metrics.as_dict()
    assert poll_metrics.by_source.get("openaq", {}).get("records_published", 0) >= 1
    assert poll_metrics.by_source.get("open-meteo", {}).get("records_published", 0) >= 1

    assert any("poll_success" in r.message for r in caplog.records)
    assert any("redpanda_publish_ok" in r.message for r in caplog.records)

    events = list(recorder.events)
    assert len(events) >= 2
    aq_events = [e for e in events if e.record_kind == "air_quality"]
    wx_events = [e for e in events if e.record_kind == "weather"]
    assert len(aq_events) == 1, "expected one air-quality event from mocked OpenAQ"
    assert len(wx_events) == 1, "expected one weather event from mocked Open-Meteo"
    aq_event = aq_events[0]
    wx_event = wx_events[0]
    assert aq_event.event_id
    assert wx_event.event_id
    assert aq_event.source == "openaq"
    assert wx_event.source == "open-meteo"

    # --- 4–6: consumer → PostgreSQL + raw object storage ---
    first = _run_consumer(
        brokers=smoke_brokers,
        topics=[aq_topic, wx_topic],
        group_id=group_a,
        store=smoke_minio,
        max_messages=2,
    )
    assert first.metrics.consumed == 2
    assert first.metrics.processed == 2
    assert first.metrics.rejected == 0
    assert first.metrics.failed == 0

    assert any("processing_ok" in r.message for r in caplog.records)
    assert any("postgres_write_ok" in r.message for r in caplog.records)
    assert any("s3_put_ok" in r.message for r in caplog.records)

    with Session(smoke_engine) as session:
        assert _count(session, AirQualityObservation) == 1
        assert _count(session, WeatherObservation) == 1
        assert _count(session, IngestionPayload) == 2

        aq_row = session.scalar(
            select(AirQualityObservation).where(
                AirQualityObservation.raw_record_id == aq_event.event_id
            )
        )
        assert aq_row is not None
        assert aq_row.pollutant == "pm25"
        assert float(aq_row.value) == 87.5

        wx_row = session.scalar(
            select(WeatherObservation).where(WeatherObservation.raw_record_id == wx_event.event_id)
        )
        assert wx_row is not None
        assert wx_row.temperature_c is not None
        assert float(wx_row.temperature_c) == 28.5

    aq_key = build_raw_object_key(
        record_kind="air_quality",
        source="openaq",
        event_id=aq_event.event_id,
        event_timestamp=aq_event.observed_at,
    )
    wx_key = build_raw_object_key(
        record_kind="weather",
        source="open-meteo",
        event_id=wx_event.event_id,
        event_timestamp=wx_event.observed_at,
    )
    assert smoke_minio.exists(key=aq_key)
    assert smoke_minio.exists(key=wx_key)

    aq_doc = _s3_get_json(smoke_minio, aq_key)
    wx_doc = _s3_get_json(smoke_minio, wx_key)
    assert aq_doc["event_id"] == aq_event.event_id
    assert aq_doc["record_kind"] == "air_quality"
    assert "raw" in aq_doc
    assert wx_doc["event_id"] == wx_event.event_id
    assert wx_doc["record_kind"] == "weather"

    # --- 7: duplicate events do not create duplicate DB rows ---
    dup_publisher = RedpandaPublisher(
        brokers=smoke_brokers,
        air_quality_topic=aq_topic,
        weather_topic=wx_topic,
        client_id=f"lahore-aqi-smoke-dup-{run_id}",
    )
    for event in (aq_event, wx_event):
        dup_publisher.publish(event)
    dup_publisher.close()

    second = _run_consumer(
        brokers=smoke_brokers,
        topics=[aq_topic, wx_topic],
        group_id=group_b,
        store=smoke_minio,
        max_messages=4,  # prior 2 + republished 2 (earliest → all four)
    )
    assert second.metrics.consumed == 4
    # First two already in PG/S3 → duplicate; exact split depends on processing.
    assert second.metrics.processed + second.metrics.duplicate == 4
    assert second.metrics.duplicate >= 2
    assert second.metrics.failed == 0

    with Session(smoke_engine) as session:
        assert _count(session, AirQualityObservation) == 1
        assert _count(session, WeatherObservation) == 1
        assert _count(session, IngestionPayload) == 2

    # --- 8: invalid events are rejected (no crash, no silent drop of valid sinks) ---
    from confluent_kafka import Producer

    bad_producer = Producer(
        {
            "bootstrap.servers": smoke_brokers,
            "client.id": f"lahore-aqi-smoke-bad-{run_id}",
            "acks": "all",
        }
    )
    bad_producer.produce(aq_topic, key=b"invalid-1", value=b"not-json-at-all")
    bad_producer.produce(
        aq_topic,
        key=b"invalid-2",
        value=json.dumps({"event_id": "x", "schema": {"name": "wrong", "version": "0"}}).encode(),
    )
    remaining = bad_producer.flush(15)
    assert remaining == 0

    third = _run_consumer(
        brokers=smoke_brokers,
        topics=[aq_topic, wx_topic],
        group_id=group_c,
        store=smoke_minio,
        max_messages=6,  # 4 prior valid + 2 invalid
    )
    assert third.metrics.consumed == 6
    assert third.metrics.rejected == 2
    assert third.metrics.failed == 0
    assert any("event_rejected" in r.message for r in caplog.records)

    with Session(smoke_engine) as session:
        # Still exactly one AQ + one weather observation.
        assert _count(session, AirQualityObservation) == 1
        assert _count(session, WeatherObservation) == 1
        assert _count(session, IngestionPayload) == 2

    # --- 9: useful logs present ---
    messages = [r.message for r in caplog.records]
    for expected in (
        "poll_cycle_started",
        "poll_success",
        "redpanda_publish_ok",
        "consumer_started",
        "processing_ok",
        "event_rejected",
        "consumer_stopped",
    ):
        assert any(expected in m for m in messages), f"missing log event: {expected}"

    logger.info(
        "smoke_pipeline_ok",
        extra={
            "aq_event_id": aq_event.event_id,
            "wx_event_id": wx_event.event_id,
            "aq_s3_key": aq_key,
            "wx_s3_key": wx_key,
            "topics": [aq_topic, wx_topic],
        },
    )


def test_smoke_invalid_payload_rejected_in_isolation(
    smoke_settings,
    smoke_engine: Engine,
    smoke_schema: None,
    smoke_minio: S3ObjectStore,
) -> None:
    """Processor rejects malformed JSON without writing sinks (no Kafka required)."""
    processor = EventProcessor(
        object_store=smoke_minio,
        postgres_writer=PostgresObservationWriter(get_session_factory()),
    )
    result = processor.process(b"{not-valid")
    assert result.status == "rejected"
    assert result.failed_stage == "validate"
    assert result.s3_ok is False
    assert result.postgres_ok is False

    with Session(smoke_engine) as session:
        assert _count(session, IngestionPayload) == 0
