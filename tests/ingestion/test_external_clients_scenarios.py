"""Mocked scenario suite for external data clients.

These tests never call real APIs. They cover the contract checklist used by the
integration-test layer documentation.

Scenarios:
1. Successful OpenAQ response
2. Empty OpenAQ response
3. Invalid OpenAQ response
4. HTTP failure
5. Rate-limit response
6. Successful Open-Meteo response
7. Missing weather values
8. Invalid weather response
9. Timeout
10. Retry behavior
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from lahore_aqi_poller.clients.openaq import (
    OpenAQAPIError,
    OpenAQClient,
    OpenAQRateLimitError,
    OpenAQTransientError,
)
from lahore_aqi_poller.clients.openaq.models import OpenAQLocation
from lahore_aqi_poller.clients.openmeteo import (
    OpenMeteoAPIError,
    OpenMeteoClient,
    OpenMeteoTransientError,
    normalize_hourly,
)
from tests.ingestion.fixtures.openaq_payloads import (
    latest_empty_response,
    latest_success_response,
    location_payload,
    locations_empty_response,
    locations_success_response,
)
from tests.ingestion.fixtures.openmeteo_payloads import (
    forecast_success_response,
    forecast_with_missing_values,
    invalid_forecast_response,
)

OpenAQFactory = Callable[..., OpenAQClient]
OpenMeteoFactory = Callable[..., OpenMeteoClient]


# ---------------------------------------------------------------------------
# 1–5 OpenAQ
# ---------------------------------------------------------------------------


def test_01_successful_openaq_response(openaq_client_factory: OpenAQFactory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v3/locations":
            return httpx.Response(200, json=locations_success_response())
        if request.url.path == "/v3/locations/9001/latest":
            return httpx.Response(200, json=latest_success_response())
        return httpx.Response(404, json={"detail": "not found"})

    with openaq_client_factory(handler) as client:
        bundles = client.fetch_recent_measurements()

    assert len(bundles) == 1
    obs = bundles[0].observation
    assert obs.pollutant == "pm25"
    assert float(obs.value) == 87.5
    assert obs.source == "openaq"
    assert obs.observed_at == datetime(2026, 10, 24, 5, 0, tzinfo=UTC)
    assert bundles[0].raw_payload["sensorsId"] == 501


def test_02_empty_openaq_response(openaq_client_factory: OpenAQFactory) -> None:
    def discover_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=locations_empty_response())

    with openaq_client_factory(discover_handler) as client:
        locations = client.discover_lahore_locations()
    assert locations == []

    def latest_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=latest_empty_response())

    location = OpenAQLocation.model_validate(location_payload())
    with openaq_client_factory(latest_handler) as client:
        raw = client.fetch_location_latest_raw(location.id)
        bundles = client.normalize_measurements(raw, location=location, mode="latest")

    assert raw == []
    assert bundles == []


def test_03_invalid_openaq_response() -> None:
    location = OpenAQLocation.model_validate(location_payload())
    # Malformed row (missing datetime/value) is skipped; valid companion kept.
    mixed: list[dict[str, Any]] = [
        {"sensorsId": 501, "locationsId": 9001},
        latest_success_response()["results"][0],
    ]
    bundles = OpenAQClient.normalize_measurements(mixed, location=location, mode="latest")
    assert len(bundles) == 1
    assert bundles[0].observation.pollutant == "pm25"


def test_04_openaq_http_failure(openaq_client_factory: OpenAQFactory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "upstream failure"})

    with openaq_client_factory(handler, max_retries=0) as client:
        with pytest.raises(OpenAQTransientError):
            client.list_locations(iso="PK")


def test_05_openaq_rate_limit_response(
    openaq_client_factory: OpenAQFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("lahore_aqi_poller.clients.openaq.client.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "0", "x-ratelimit-reset": "0"},
            json={"detail": "Too many requests"},
        )

    with openaq_client_factory(handler, max_retries=2) as client:
        with pytest.raises(OpenAQRateLimitError):
            client.list_locations(iso="PK")
    assert calls["n"] == 3


# ---------------------------------------------------------------------------
# 6–8 Open-Meteo
# ---------------------------------------------------------------------------


def test_06_successful_openmeteo_response(
    openmeteo_client_factory: OpenMeteoFactory,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/forecast"
        return httpx.Response(200, json=forecast_success_response())

    with openmeteo_client_factory(handler) as client:
        bundles = client.fetch_forecast(forecast_days=1, past_days=0)

    assert len(bundles) >= 2  # current + hourly
    current = bundles[0].observation
    assert current.source == "open-meteo"
    assert float(current.temperature_c) == 28.5
    assert float(current.wind_speed_ms) == 3.2
    assert bundles[0].raw_payload["kind"] == "current"


def test_07_missing_weather_values() -> None:
    bundles = normalize_hourly(
        forecast_with_missing_values(),
        request_latitude=31.5204,
        request_longitude=74.3587,
        kind="forecast_hourly",
    )
    assert len(bundles) == 2
    first = bundles[0].observation
    assert float(first.temperature_c) == 27.0
    assert first.precipitation_mm is None
    second = bundles[1].observation
    assert second.temperature_c is None
    assert float(second.precipitation_mm) == 0.2


def test_08_invalid_weather_response(
    openmeteo_client_factory: OpenMeteoFactory,
) -> None:
    # Validation failure during normalize → empty list (graceful)
    bundles = normalize_hourly(
        invalid_forecast_response(),
        request_latitude=31.5204,
        request_longitude=74.3587,
    )
    assert bundles == []

    # API-level error payload
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": True, "reason": "Latitude must be in range of -90 to 90°"},
        )

    with openmeteo_client_factory(handler) as client:
        with pytest.raises(OpenMeteoAPIError, match="Latitude"):
            client.fetch_forecast_raw()


# ---------------------------------------------------------------------------
# 9–10 Timeout + retry (both clients)
# ---------------------------------------------------------------------------


def test_09_timeout_openaq_and_openmeteo(
    openaq_client_factory: OpenAQFactory,
    openmeteo_client_factory: OpenMeteoFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("lahore_aqi_poller.clients.openaq.client.time.sleep", lambda _s: None)
    monkeypatch.setattr("lahore_aqi_poller.clients.openmeteo.client.time.sleep", lambda _s: None)

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    with openaq_client_factory(timeout_handler, max_retries=1) as client:
        with pytest.raises(OpenAQTransientError, match="timed out"):
            client.list_locations(iso="PK")

    with openmeteo_client_factory(timeout_handler, max_retries=1) as client:
        with pytest.raises(OpenMeteoTransientError, match="timed out"):
            client.fetch_forecast_raw()


def test_10_retry_behavior_succeeds_after_transient_failure(
    openaq_client_factory: OpenAQFactory,
    openmeteo_client_factory: OpenMeteoFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("lahore_aqi_poller.clients.openaq.client.time.sleep", lambda _s: None)
    monkeypatch.setattr("lahore_aqi_poller.clients.openmeteo.client.time.sleep", lambda _s: None)

    openaq_calls = {"n": 0}

    def openaq_handler(request: httpx.Request) -> httpx.Response:
        openaq_calls["n"] += 1
        if openaq_calls["n"] == 1:
            return httpx.Response(503, json={"detail": "unavailable"})
        return httpx.Response(200, json=locations_success_response())

    with openaq_client_factory(openaq_handler, max_retries=2) as client:
        locations = client.list_locations(iso="PK")
    assert openaq_calls["n"] == 2
    assert len(locations) == 1

    meteo_calls = {"n": 0}

    def meteo_handler(request: httpx.Request) -> httpx.Response:
        meteo_calls["n"] += 1
        if meteo_calls["n"] == 1:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json=forecast_success_response())

    with openmeteo_client_factory(meteo_handler, max_retries=2) as client:
        raw = client.fetch_forecast_raw(forecast_days=1, past_days=0)
    assert meteo_calls["n"] == 2
    assert "hourly" in raw


def test_openaq_client_http_error_is_api_error(
    openaq_client_factory: OpenAQFactory,
) -> None:
    """Non-retryable 4xx is surfaced as OpenAQAPIError (HTTP failure variant)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": [{"msg": "invalid"}]})

    with openaq_client_factory(handler) as client, pytest.raises(OpenAQAPIError) as exc_info:
        client.list_locations(iso="PK")
    assert exc_info.value.status_code == 422
