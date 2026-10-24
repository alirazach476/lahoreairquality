"""Controlled failure simulations + recovery assertions for the ingestion pipeline.

Each scenario documents detect → log → retry → no silent loss → recover → status.
Contracts live in ``lahore_air_quality.resilience.scenarios`` and ``docs/failure-recovery.md``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from lahore_air_quality.db.health import DatabaseHealth
from lahore_air_quality.quality.classify import classify_air_quality
from lahore_air_quality.quality.report import build_air_quality_report
from lahore_air_quality.quality.rules import (
    find_missing_intervals,
    is_delayed_ingest,
    is_stale,
    rule_delayed_ingest,
    rule_missing_value,
)
from lahore_air_quality.quality.thresholds import (
    DELAYED_INGEST_AFTER,
    EXPECTED_AQ_INTERVAL,
    GAP_FACTOR,
    STALE_AFTER,
)
from lahore_air_quality.quality.types import AirQualityRecord, QualityClass
from lahore_air_quality.resilience import (
    ComponentStatus,
    ScenarioId,
    build_pipeline_status,
    get_scenario,
    list_scenarios,
)
from lahore_aqi_consumer.processing import EventProcessor
from lahore_aqi_consumer.service import ConsumerService
from lahore_aqi_consumer.storage.postgres import (
    PermanentPostgresWriteError,
    PostgresObservationWriter,
)
from lahore_aqi_poller.clients.openaq.exceptions import OpenAQAPIError
from lahore_aqi_poller.clients.openaq.models import (
    NormalizedAirQualityObservation,
    ObservationBundle,
)
from lahore_aqi_poller.clients.openmeteo.exceptions import OpenMeteoAPIError
from lahore_aqi_poller.clients.openmeteo.models import (
    NormalizedWeatherObservation,
    WeatherObservationBundle,
)
from lahore_aqi_poller.producers import RecordingPublisher
from lahore_aqi_poller.producers.redpanda import ProducerHealth, RedpandaPublishError
from lahore_aqi_poller.service import PollerService

from tests.resilience.conftest import FakeObjectStore, dumps, make_envelope, pg_writer


def test_scenario_catalog_covers_ten_modes() -> None:
    scenarios = list_scenarios()
    assert len(scenarios) == 10
    ids = {s.id for s in scenarios}
    assert ids == set(ScenarioId)
    for scenario in scenarios:
        assert scenario.detect
        assert scenario.data_loss_policy
        assert scenario.recovery
        assert scenario.status_surface


# ---------------------------------------------------------------------------
# 1. OpenAQ unavailable
# ---------------------------------------------------------------------------


def _aq_bundle(raw_record_id: str = "openaq:501:abc") -> ObservationBundle:
    return ObservationBundle(
        observation=NormalizedAirQualityObservation(
            observation_id="obs-1",
            station_id="9001",
            location_name="Lahore",
            latitude=Decimal("31.560100"),
            longitude=Decimal("74.335900"),
            pollutant="pm25",
            value=Decimal("42.5"),
            unit="µg/m³",
            observed_at=datetime(2026, 10, 24, 5, 0, tzinfo=UTC),
            source="openaq",
            raw_record_id=raw_record_id,
        ),
        raw_payload={"value": 42.5},
    )


def _wx_bundle() -> WeatherObservationBundle:
    return WeatherObservationBundle(
        observation=NormalizedWeatherObservation(
            observed_at=datetime(2026, 10, 24, 5, 0, tzinfo=UTC),
            latitude=Decimal("31.520400"),
            longitude=Decimal("74.358700"),
            temperature_c=Decimal("28.50"),
            relative_humidity_pct=Decimal("55.00"),
            precipitation_mm=Decimal("0.000"),
            wind_speed_ms=Decimal("3.200"),
            wind_direction_deg=Decimal("180.00"),
            pressure_hpa=Decimal("1008.20"),
            source="open-meteo",
            raw_record_id="openmeteo:current:abc",
        ),
        raw_payload={"temperature_2m": 28.5},
    )


def test_openaq_unavailable_isolates_and_recovers() -> None:
    scenario = get_scenario(ScenarioId.OPENAQ_UNAVAILABLE)
    assert "poll_failed" in scenario.log_events

    openaq = MagicMock()
    openaq.fetch_recent_measurements.side_effect = [
        OpenAQAPIError("503 service unavailable"),
        [_aq_bundle()],
    ]
    openmeteo = MagicMock()
    openmeteo.fetch_current.return_value = _wx_bundle()
    publisher = RecordingPublisher()
    service = PollerService(
        openaq_client=openaq,
        openmeteo_client=openmeteo,
        publisher=publisher,
        interval_seconds=60.0,
    )

    first = service.poll_once()
    assert first.failed_polls >= 1
    # Weather still published — no silent total outage.
    assert first.records_published >= 1
    assert any(e.source == "open-meteo" for e in publisher.events)

    second = service.poll_once()
    assert second.successful_polls >= 1
    assert any(e.source == "openaq" for e in publisher.events)


# ---------------------------------------------------------------------------
# 2. Open-Meteo unavailable
# ---------------------------------------------------------------------------


def test_openmeteo_unavailable_isolates_and_recovers() -> None:
    openaq = MagicMock()
    openaq.fetch_recent_measurements.return_value = [_aq_bundle()]
    openmeteo = MagicMock()
    openmeteo.fetch_current.side_effect = [
        OpenMeteoAPIError("timeout"),
        _wx_bundle(),
    ]
    publisher = RecordingPublisher()
    service = PollerService(
        openaq_client=openaq,
        openmeteo_client=openmeteo,
        publisher=publisher,
        interval_seconds=60.0,
    )

    first = service.poll_once()
    assert first.failed_polls >= 1
    assert any(e.source == "openaq" for e in publisher.events)

    second = service.poll_once()
    assert any(e.source == "open-meteo" for e in publisher.events)
    assert second.records_published >= 1


# ---------------------------------------------------------------------------
# 3. Redpanda unavailable
# ---------------------------------------------------------------------------


def test_redpanda_unavailable_publish_logged_no_fabricated_rows() -> None:
    openaq = MagicMock()
    openaq.fetch_recent_measurements.return_value = [_aq_bundle()]
    openmeteo = MagicMock()
    openmeteo.fetch_current.return_value = None

    publisher = MagicMock()
    publisher.publish.side_effect = RedpandaPublishError("broker down")
    publisher.health_check.return_value = ProducerHealth(
        healthy=False,
        message="connection refused",
        brokers="redpanda:9092",
    )
    service = PollerService(
        openaq_client=openaq,
        openmeteo_client=openmeteo,
        publisher=publisher,
        interval_seconds=60.0,
        enable_openmeteo=False,
    )
    metrics = service.poll_once()
    assert metrics.records_received >= 1
    assert metrics.records_rejected >= 1
    assert metrics.records_published == 0
    health = publisher.health_check()
    assert health.healthy is False


def test_redpanda_unavailable_consumer_does_not_commit() -> None:
    store = FakeObjectStore()
    processor = EventProcessor(object_store=store, postgres_writer=pg_writer())
    commits: list[Any] = []

    class ErrMsg:
        def error(self) -> str:
            return "Broker: Not available"

        def value(self) -> bytes:
            return b""

        def topic(self) -> str:
            return "aq.raw"

        def partition(self) -> int:
            return 0

        def offset(self) -> int:
            return 1

    class FakeConsumer:
        def __init__(self) -> None:
            self._queue = [ErrMsg()]
            self.closed = False

        def subscribe(self, _topics: list[str]) -> None:
            return None

        def poll(self, _timeout: float) -> Any:
            return self._queue.pop(0) if self._queue else None

        def commit(self, message: Any = None, asynchronous: bool = False) -> None:
            commits.append(message)

        def close(self) -> None:
            self.closed = True

    service = ConsumerService(
        processor=processor,
        consumer=FakeConsumer(),
        topics=["aq.raw"],
        poll_timeout_seconds=0.01,
        retry_backoff_seconds=0.01,
        max_retry_backoff_seconds=0.01,
    )
    service.run(max_messages=1)
    assert commits == []
    assert service.metrics.failed >= 1


# ---------------------------------------------------------------------------
# 4. PostgreSQL unavailable (+ recovery)
# ---------------------------------------------------------------------------


def test_postgres_unavailable_holds_offset_then_recovers() -> None:
    store = FakeObjectStore()
    pg = pg_writer(fail_once=True)
    processor = EventProcessor(object_store=store, postgres_writer=pg)
    payload = dumps(make_envelope())

    first = processor.process(payload)
    assert first.status == "failed"
    assert first.failed_stage == "postgres"
    assert first.s3_ok is True
    assert first.s3_key in store.objects

    second = processor.process(payload)
    assert second.status in {"processed", "duplicate"}
    assert second.postgres_ok is True


def test_postgres_unavailable_status_surface() -> None:
    snap = build_pipeline_status(
        database_checker=lambda: DatabaseHealth(
            healthy=False,
            message="connection refused",
            details={"error_type": "OperationalError"},
        )
    )
    assert snap.overall_healthy is False
    assert snap.components[0].name == "postgres"
    assert snap.components[0].healthy is False


# ---------------------------------------------------------------------------
# 5. Object storage unavailable (+ recovery)
# ---------------------------------------------------------------------------


def test_object_storage_unavailable_skips_postgres_then_recovers() -> None:
    store = FakeObjectStore()
    store.fail = True
    pg = pg_writer()
    processor = EventProcessor(object_store=store, postgres_writer=pg)
    payload = dumps(make_envelope())

    first = processor.process(payload)
    assert first.status == "failed"
    assert first.failed_stage == "s3"
    pg.write.assert_not_called()

    store.fail = False
    second = processor.process(payload)
    assert second.status == "processed"
    assert second.s3_ok and second.postgres_ok
    pg.write.assert_called()


# ---------------------------------------------------------------------------
# 6. Malformed event
# ---------------------------------------------------------------------------


def test_malformed_event_envelope_rejected_no_sinks() -> None:
    store = FakeObjectStore()
    pg = pg_writer()
    processor = EventProcessor(object_store=store, postgres_writer=pg)
    result = processor.process(b'{"schema": "nope"}')
    assert result.status == "rejected"
    assert result.failed_stage == "validate"
    assert store.objects == {}
    pg.write.assert_not_called()


def test_malformed_event_normalized_shape_rejected_not_infinite_retry() -> None:
    store = FakeObjectStore()
    writer = MagicMock(spec=PostgresObservationWriter)
    writer.write.side_effect = PermanentPostgresWriteError(
        "air_quality normalized payload missing field 'station_id'"
    )
    processor = EventProcessor(object_store=store, postgres_writer=writer)
    # Valid envelope, but writer classifies permanent shape error.
    result = processor.process(dumps(make_envelope()))
    assert result.status == "rejected"
    assert result.failed_stage == "postgres_validate"
    assert result.s3_ok is True  # archived for audit
    assert result.s3_key in store.objects


def test_malformed_event_consumer_commits_reject() -> None:
    store = FakeObjectStore()
    processor = EventProcessor(object_store=store, postgres_writer=pg_writer())
    commits: list[Any] = []

    class FakeMsg:
        def error(self) -> None:
            return None

        def value(self) -> bytes:
            return b"not-json"

        def topic(self) -> str:
            return "aq.raw"

        def partition(self) -> int:
            return 0

        def offset(self) -> int:
            return 7

    class FakeConsumer:
        def __init__(self) -> None:
            self._queue = [FakeMsg()]

        def subscribe(self, _topics: list[str]) -> None:
            return None

        def poll(self, _timeout: float) -> Any:
            return self._queue.pop(0) if self._queue else None

        def commit(self, message: Any = None, asynchronous: bool = False) -> None:
            commits.append(message)

        def close(self) -> None:
            return None

    service = ConsumerService(
        processor=processor,
        consumer=FakeConsumer(),
        topics=["aq.raw"],
        poll_timeout_seconds=0.01,
        retry_backoff_seconds=0.01,
    )
    service.run(max_messages=1)
    assert len(commits) == 1
    assert service.metrics.rejected == 1


# ---------------------------------------------------------------------------
# 7. Duplicate event
# ---------------------------------------------------------------------------


def test_duplicate_event_idempotent_no_second_row_effect() -> None:
    store = FakeObjectStore()
    processor = EventProcessor(object_store=store, postgres_writer=pg_writer())
    payload = dumps(make_envelope())
    first = processor.process(payload)
    assert first.status == "processed"

    processor2 = EventProcessor(object_store=store, postgres_writer=pg_writer(duplicate=True))
    second = processor2.process(payload)
    assert second.status == "duplicate"
    assert len(store.objects) == 1


# ---------------------------------------------------------------------------
# 8. Stale sensor
# ---------------------------------------------------------------------------


def test_stale_sensor_detected_and_clears_when_fresh() -> None:
    now = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    stale_ts = now - STALE_AFTER - timedelta(hours=1)
    assert is_stale(stale_ts, now=now, stale_after=STALE_AFTER) is True
    assert is_stale(now - timedelta(hours=1), now=now, stale_after=STALE_AFTER) is False

    records = [
        AirQualityRecord(
            station_id="9001",
            pollutant="pm25",
            value=Decimal("40"),
            unit="µg/m³",
            observed_at=stale_ts,
            ingested_at=stale_ts + timedelta(minutes=5),
            source="openaq",
        )
    ]
    report = build_air_quality_report(records, now=now)
    assert report.freshness["stale"] is True

    records.append(
        AirQualityRecord(
            station_id="9001",
            pollutant="pm25",
            value=Decimal("41"),
            unit="µg/m³",
            observed_at=now - timedelta(minutes=30),
            ingested_at=now,
            source="openaq",
        )
    )
    recovered = build_air_quality_report(records, now=now)
    assert recovered.freshness["stale"] is False


# ---------------------------------------------------------------------------
# 9. Missing readings
# ---------------------------------------------------------------------------


def test_missing_readings_detected_not_imputed() -> None:
    finding = rule_missing_value(
        AirQualityRecord(
            station_id="9001",
            pollutant="pm25",
            value=None,
            unit="µg/m³",
            observed_at=datetime(2026, 10, 24, 5, 0, tzinfo=UTC),
        )
    )
    assert finding
    assert finding[0].rule_id == "missing_value"

    classified = classify_air_quality(
        AirQualityRecord(
            station_id="9001",
            pollutant="pm25",
            value=None,
            unit="µg/m³",
            observed_at=datetime(2026, 10, 24, 5, 0, tzinfo=UTC),
        )
    )
    assert classified.quality_class is QualityClass.INVALID

    t0 = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    timestamps = [t0, t0 + timedelta(hours=1), t0 + timedelta(hours=10)]
    gaps = find_missing_intervals(
        timestamps, expected=EXPECTED_AQ_INTERVAL, gap_factor=GAP_FACTOR
    )
    assert gaps
    # Never invent filler observations — only report the gap.
    assert gaps[0][2] >= 9.0


def test_missing_readings_empty_poll_logged_via_metrics() -> None:
    openaq = MagicMock()
    openaq.fetch_recent_measurements.return_value = []
    publisher = RecordingPublisher()
    service = PollerService(
        openaq_client=openaq,
        openmeteo_client=None,
        publisher=publisher,
        interval_seconds=60.0,
        enable_openmeteo=False,
    )
    metrics = service.poll_once()
    assert metrics.successful_polls == 1
    assert metrics.records_published == 0
    assert publisher.events == []


# ---------------------------------------------------------------------------
# 10. Delayed event
# ---------------------------------------------------------------------------


def test_delayed_event_flagged_but_retained() -> None:
    observed = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    ingested = observed + DELAYED_INGEST_AFTER + timedelta(hours=2)
    assert is_delayed_ingest(observed, ingested) is True

    record = AirQualityRecord(
        station_id="9001",
        pollutant="pm25",
        value=Decimal("55"),
        unit="µg/m³",
        observed_at=observed,
        ingested_at=ingested,
        source="openaq",
    )
    findings = rule_delayed_ingest(record)
    assert findings and findings[0].rule_id == "delayed_ingest"

    result = classify_air_quality(record)
    assert "delayed_ingest" in result.rule_ids
    assert result.quality_class is QualityClass.SUSPECT

    report = build_air_quality_report([record], now=ingested)
    assert report.freshness["delayed_ingest_count"] == 1
    assert report.freshness["max_ingest_delay_hours"] is not None
    assert report.freshness["max_ingest_delay_hours"] > 6.0


# ---------------------------------------------------------------------------
# Status API surface (catalog)
# ---------------------------------------------------------------------------


def test_pipeline_status_includes_optional_probes() -> None:
    snap = build_pipeline_status(
        database_checker=lambda: DatabaseHealth(healthy=True, message="ok"),
        redpanda_probe=lambda: ComponentStatus(
            name="redpanda", healthy=True, message="Healthy"
        ),
        object_store_probe=lambda: ComponentStatus(
            name="object_storage", healthy=False, message="MinIO down"
        ),
    )
    assert snap.overall_healthy is False
    names = {c.name for c in snap.components}
    assert names == {"postgres", "redpanda", "object_storage"}
    assert snap.scenario_catalog_size == 10


@pytest.mark.parametrize("scenario_id", list(ScenarioId))
def test_each_scenario_has_nonempty_contract(scenario_id: ScenarioId) -> None:
    scenario = get_scenario(scenario_id)
    assert scenario.title
    assert scenario.retry or scenario.id in {
        ScenarioId.STALE_SENSOR,
        ScenarioId.DELAYED_EVENT,
        ScenarioId.DUPLICATE_EVENT,
        ScenarioId.MALFORMED_EVENT,
    }
