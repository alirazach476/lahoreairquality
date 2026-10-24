"""Tests for the polling service (mocked API clients; no Redpanda/Postgres)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

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
from lahore_aqi_poller.service import PollerService


def _aq_bundle(
    *,
    raw_record_id: str = "openaq:501:abc",
    value: Decimal = Decimal("42.5"),
) -> ObservationBundle:
    return ObservationBundle(
        observation=NormalizedAirQualityObservation(
            observation_id="obs-1",
            station_id="9001",
            location_name="Lahore",
            latitude=Decimal("31.560100"),
            longitude=Decimal("74.335900"),
            pollutant="pm25",
            value=value,
            unit="µg/m³",
            observed_at=datetime(2026, 10, 24, 5, 0, tzinfo=UTC),
            source="openaq",
            raw_record_id=raw_record_id,
        ),
        raw_payload={"sensorsId": 501, "value": float(value)},
    )


def _wx_bundle(
    *,
    raw_record_id: str = "openmeteo:current:abc",
) -> WeatherObservationBundle:
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
            raw_record_id=raw_record_id,
        ),
        raw_payload={"kind": "current", "temperature_2m": 28.5},
    )


def _service(
    *,
    openaq: MagicMock | None = None,
    openmeteo: MagicMock | None = None,
    publisher: RecordingPublisher | None = None,
    enable_openaq: bool = True,
    enable_openmeteo: bool = True,
) -> tuple[PollerService, RecordingPublisher]:
    pub = publisher or RecordingPublisher()
    service = PollerService(
        openaq_client=openaq,
        openmeteo_client=openmeteo,
        publisher=pub,
        interval_seconds=60.0,
        enable_openaq=enable_openaq,
        enable_openmeteo=enable_openmeteo,
    )
    return service, pub


def test_successful_poll_publishes_idempotent_events() -> None:
    openaq = MagicMock()
    openaq.fetch_recent_measurements.return_value = [_aq_bundle()]
    openmeteo = MagicMock()
    openmeteo.fetch_current.return_value = _wx_bundle()

    service, publisher = _service(openaq=openaq, openmeteo=openmeteo)
    metrics = service.poll_once()

    assert metrics.successful_polls == 2
    assert metrics.failed_polls == 0
    assert metrics.records_received == 2
    assert metrics.records_rejected == 0
    assert metrics.records_published == 2
    assert len(publisher.events) == 2

    aq_event = next(e for e in publisher.events if e.source == "openaq")
    assert aq_event.event_id == aq_event.idempotency_key == "openaq:501:abc"
    assert aq_event.record_kind == "air_quality"
    assert aq_event.ingested_at.tzinfo is not None
    assert aq_event.raw["sensorsId"] == 501
    assert aq_event.normalized["pollutant"] == "pm25"
    assert "value" in aq_event.normalized

    wx_event = next(e for e in publisher.events if e.source == "open-meteo")
    assert wx_event.event_id == "openmeteo:current:abc"
    assert wx_event.raw["temperature_2m"] == 28.5


def test_failed_api_does_not_stop_other_source() -> None:
    openaq = MagicMock()
    openaq.fetch_recent_measurements.side_effect = OpenAQAPIError(
        "boom", status_code=500, path="/v3/locations"
    )
    openmeteo = MagicMock()
    openmeteo.fetch_current.return_value = _wx_bundle()

    service, publisher = _service(openaq=openaq, openmeteo=openmeteo)
    metrics = service.poll_once()

    assert metrics.failed_polls == 1
    assert metrics.successful_polls == 1
    assert metrics.records_published == 1
    assert publisher.events[0].source == "open-meteo"

    # Weather failure should not block AQ either.
    openaq2 = MagicMock()
    openaq2.fetch_recent_measurements.return_value = [_aq_bundle()]
    openmeteo2 = MagicMock()
    openmeteo2.fetch_current.side_effect = OpenMeteoAPIError("wx down", status_code=503)

    service2, publisher2 = _service(openaq=openaq2, openmeteo=openmeteo2)
    metrics2 = service2.poll_once()
    assert metrics2.successful_polls == 1
    assert metrics2.failed_polls == 1
    assert publisher2.events[0].source == "openaq"


def test_empty_result_is_successful_poll_with_zero_records() -> None:
    openaq = MagicMock()
    openaq.fetch_recent_measurements.return_value = []
    openmeteo = MagicMock()
    openmeteo.fetch_current.return_value = None

    service, publisher = _service(openaq=openaq, openmeteo=openmeteo)
    metrics = service.poll_once()

    assert metrics.successful_polls == 2
    assert metrics.failed_polls == 0
    assert metrics.records_received == 0
    assert metrics.records_published == 0
    assert publisher.events == []


def test_malformed_record_is_rejected_not_fabricated() -> None:
    bad_aq = _aq_bundle(raw_record_id="openaq:bad")
    # Force an unusable identity after construction via model copy.
    bad_aq = bad_aq.model_copy(
        update={"observation": bad_aq.observation.model_copy(update={"raw_record_id": ""})}
    )
    openaq = MagicMock()
    openaq.fetch_recent_measurements.return_value = [bad_aq, _aq_bundle()]

    # Weather with no measurements must be rejected.
    empty_wx = _wx_bundle(raw_record_id="openmeteo:empty")
    empty_wx = empty_wx.model_copy(
        update={
            "observation": empty_wx.observation.model_copy(
                update={
                    "temperature_c": None,
                    "relative_humidity_pct": None,
                    "precipitation_mm": None,
                    "wind_speed_ms": None,
                    "wind_direction_deg": None,
                    "pressure_hpa": None,
                }
            )
        }
    )
    openmeteo = MagicMock()
    openmeteo.fetch_current.return_value = empty_wx

    service, publisher = _service(openaq=openaq, openmeteo=openmeteo)
    metrics = service.poll_once()

    assert metrics.records_received == 3  # 2 AQ + 1 weather
    assert metrics.records_rejected == 2
    assert metrics.records_published == 1
    assert len(publisher.events) == 1
    assert publisher.events[0].event_id == "openaq:501:abc"


def test_graceful_shutdown_stops_run_loop() -> None:
    openaq = MagicMock()
    openaq.fetch_recent_measurements.return_value = []
    openmeteo = MagicMock()
    openmeteo.fetch_current.return_value = None

    service, _publisher = _service(openaq=openaq, openmeteo=openmeteo)
    service._interval_seconds = 30.0  # noqa: SLF001 — keep wait long; shutdown interrupts

    done = threading.Event()
    result: list[object] = []

    def _run() -> None:
        metrics = service.run(once=False)
        result.append(metrics)
        done.set()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    # Allow first poll to start/finish, then request shutdown during wait.
    threading.Event().wait(0.2)
    service.request_shutdown()
    assert done.wait(timeout=5.0), "poller did not shut down gracefully"
    thread.join(timeout=1.0)
    assert result
    assert openaq.fetch_recent_measurements.called


def test_disabled_source_is_skipped() -> None:
    openaq = MagicMock()
    openmeteo = MagicMock()
    service, publisher = _service(
        openaq=openaq,
        openmeteo=openmeteo,
        enable_openaq=False,
        enable_openmeteo=True,
    )
    openmeteo.fetch_current.return_value = _wx_bundle()
    service.poll_once()
    openaq.fetch_recent_measurements.assert_not_called()
    assert len(publisher.events) == 1
