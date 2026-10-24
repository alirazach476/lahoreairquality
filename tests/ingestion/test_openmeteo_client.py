"""Unit tests for the Open-Meteo client using mocked HTTP responses."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest

from lahore_aqi_poller.clients.openmeteo import (
    OpenMeteoAPIError,
    OpenMeteoClient,
    OpenMeteoConfigError,
    OpenMeteoTransientError,
    normalize_hourly,
)

LAHORE_LAT = 31.5204
LAHORE_LON = 74.3587


def _forecast_payload(*, with_nulls: bool = False) -> dict[str, Any]:
    temp = [28.5, None if with_nulls else 29.0]
    return {
        "latitude": 31.5,
        "longitude": 74.375,
        "generationtime_ms": 0.12,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "elevation": 217.0,
        "current_units": {
            "time": "iso8601",
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "precipitation": "mm",
            "wind_speed_10m": "m/s",
            "wind_direction_10m": "°",
            "surface_pressure": "hPa",
        },
        "current": {
            "time": "2026-10-24T05:00",
            "interval": 900,
            "temperature_2m": 28.5,
            "relative_humidity_2m": 55,
            "precipitation": 0.0,
            "wind_speed_10m": 3.2,
            "wind_direction_10m": 180,
            "surface_pressure": 1008.2,
        },
        "hourly_units": {
            "time": "iso8601",
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "precipitation": "mm",
            "wind_speed_10m": "m/s",
            "wind_direction_10m": "°",
            "surface_pressure": "hPa",
        },
        "hourly": {
            "time": ["2026-10-24T00:00", "2026-10-24T01:00"],
            "temperature_2m": temp,
            "relative_humidity_2m": [50, 52],
            "precipitation": [0.0, 0.1],
            "wind_speed_10m": [2.5, 2.8],
            "wind_direction_10m": [90, 100],
            "surface_pressure": [1008.0, 1007.5],
        },
    }


def _archive_payload() -> dict[str, Any]:
    return {
        "latitude": 31.5,
        "longitude": 74.375,
        "timezone": "GMT",
        "hourly_units": {"temperature_2m": "°C", "wind_speed_10m": "m/s"},
        "hourly": {
            "time": ["2026-10-01T00:00"],
            "temperature_2m": [27.0],
            "relative_humidity_2m": [60],
            "precipitation": [None],  # missing value handled
            "wind_speed_10m": [1.5],
            "wind_direction_10m": [45],
            "surface_pressure": [1005.0],
        },
    }


def _make_client(handler: Any, **kwargs: Any) -> OpenMeteoClient:
    transport = httpx.MockTransport(handler)
    return OpenMeteoClient(
        latitude=kwargs.pop("latitude", LAHORE_LAT),
        longitude=kwargs.pop("longitude", LAHORE_LON),
        forecast_base_url="https://api.open-meteo.com",
        archive_base_url="https://archive-api.open-meteo.com",
        transport=transport,
        max_retries=kwargs.pop("max_retries", 2),
        **kwargs,
    )


def test_rejects_invalid_coordinates() -> None:
    with pytest.raises(OpenMeteoConfigError):
        OpenMeteoClient(latitude=999.0, longitude=74.0)


def test_fetch_forecast_uses_configured_coordinates_and_ml_variables() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["path"] = request.url.path
        assert request.url.path == "/v1/forecast"
        assert float(request.url.params["latitude"]) == LAHORE_LAT
        assert float(request.url.params["longitude"]) == LAHORE_LON
        hourly = request.url.params["hourly"]
        for var in (
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "wind_speed_10m",
            "wind_direction_10m",
            "surface_pressure",
        ):
            assert var in hourly
        assert request.url.params["wind_speed_unit"] == "ms"
        assert request.url.params["timezone"] == "UTC"
        return httpx.Response(200, json=_forecast_payload())

    with _make_client(handler) as client:
        bundles = client.fetch_forecast(forecast_days=3, past_days=1)

    # current + 2 hourly
    assert len(bundles) == 3
    current = bundles[0].observation
    assert current.source == "open-meteo"
    assert float(current.temperature_c) == 28.5
    assert float(current.wind_speed_ms) == 3.2
    assert float(current.pressure_hpa) == 1008.2
    assert current.observed_at == datetime(2026, 10, 24, 5, 0, tzinfo=UTC)
    assert bundles[0].raw_payload["kind"] == "current"
    assert "current" in bundles[0].raw_payload


def test_fetch_historical_normalizes_and_preserves_raw() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/archive"
        assert request.url.params["start_date"] == "2026-10-01"
        assert request.url.params["end_date"] == "2026-10-02"
        return httpx.Response(200, json=_archive_payload())

    with _make_client(handler) as client:
        bundles = client.fetch_historical(
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 2),
        )

    assert len(bundles) == 1
    obs = bundles[0].observation
    assert float(obs.temperature_c) == 27.0
    assert obs.precipitation_mm is None  # missing value preserved as null
    assert bundles[0].raw_payload["precipitation"] is None
    assert bundles[0].raw_payload["temperature_2m"] == 27.0


def test_missing_all_variables_timestep_skipped() -> None:
    payload = _forecast_payload()
    payload.pop("current")
    payload["hourly"] = {
        "time": ["2026-10-24T00:00"],
        "temperature_2m": [None],
        "relative_humidity_2m": [None],
        "precipitation": [None],
        "wind_speed_10m": [None],
        "wind_direction_10m": [None],
        "surface_pressure": [None],
    }
    bundles = normalize_hourly(
        payload,
        request_latitude=LAHORE_LAT,
        request_longitude=LAHORE_LON,
    )
    assert bundles == []


def test_empty_hourly_returns_empty_list() -> None:
    payload = {
        "latitude": 31.5,
        "longitude": 74.375,
        "hourly": {"time": []},
    }
    bundles = normalize_hourly(
        payload,
        request_latitude=LAHORE_LAT,
        request_longitude=LAHORE_LON,
    )
    assert bundles == []


def test_mismatched_hourly_lengths_fail_validation() -> None:
    payload = _forecast_payload()
    payload.pop("current")
    payload["hourly"]["temperature_2m"] = [1.0]  # length mismatch
    bundles = normalize_hourly(
        payload,
        request_latitude=LAHORE_LAT,
        request_longitude=LAHORE_LON,
    )
    assert bundles == []


def test_api_error_reason_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": True, "reason": "Latitude must be in range of -90 to 90°"},
        )

    with _make_client(handler) as client, pytest.raises(OpenMeteoAPIError, match="Latitude"):
        client.fetch_forecast_raw()


def test_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"reason": "bad request"})

    with _make_client(handler) as client, pytest.raises(OpenMeteoAPIError) as exc_info:
        client.fetch_forecast_raw()
    assert exc_info.value.status_code == 400


def test_transient_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lahore_aqi_poller.clients.openmeteo.client.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="unavailable")

    with _make_client(handler, max_retries=1) as client, pytest.raises(OpenMeteoTransientError):
        client.fetch_forecast_raw()
    assert calls["n"] == 2


def test_from_settings_uses_config_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lahore_air_quality.config import Settings, get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("LAHORE_LATITUDE", "31.55")
    monkeypatch.setenv("LAHORE_LONGITUDE", "74.33")
    monkeypatch.setenv("OPENMETEO_BASE_URL", "https://api.open-meteo.com")
    monkeypatch.setenv("OPENMETEO_ARCHIVE_BASE_URL", "https://archive-api.open-meteo.com")

    settings = Settings(_env_file=None)

    def handler(request: httpx.Request) -> httpx.Response:
        assert float(request.url.params["latitude"]) == 31.55
        assert float(request.url.params["longitude"]) == 74.33
        return httpx.Response(200, json=_forecast_payload())

    transport = httpx.MockTransport(handler)
    client = OpenMeteoClient(
        latitude=settings.lahore_latitude,
        longitude=settings.lahore_longitude,
        forecast_base_url=settings.openmeteo_base_url,
        archive_base_url=settings.openmeteo_archive_base_url,
        transport=transport,
    )
    with client:
        raw = client.fetch_forecast_raw(forecast_days=1, past_days=0)
    assert "hourly" in raw
    get_settings.cache_clear()


def test_historical_datetime_helper() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["start_date"] == "2026-09-30"
        assert request.url.params["end_date"] == "2026-10-01"
        return httpx.Response(200, json=_archive_payload())

    with _make_client(handler) as client:
        bundles = client.fetch_historical_for_datetimes(
            datetime_from=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
            datetime_to=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        )
    assert len(bundles) == 1
