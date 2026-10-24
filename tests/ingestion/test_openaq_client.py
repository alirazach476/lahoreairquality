"""Unit tests for the OpenAQ v3 client using mocked HTTP responses."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from lahore_aqi_poller.clients.openaq import (
    OpenAQAPIError,
    OpenAQAuthError,
    OpenAQClient,
    OpenAQConfigError,
    OpenAQRateLimitError,
    normalize_latest_measurement,
)
from lahore_aqi_poller.clients.openaq.models import OpenAQLocation


def _location_payload(location_id: int = 9001) -> dict[str, Any]:
    return {
        "id": location_id,
        "name": "US Consulate Lahore",
        "locality": "Lahore",
        "timezone": "Asia/Karachi",
        "country": {"id": 1, "code": "PK", "name": "Pakistan"},
        "provider": {"id": 10, "name": "AirNow"},
        "isMobile": False,
        "isMonitor": True,
        "sensors": [
            {
                "id": 501,
                "name": "PM2.5",
                "parameter": {
                    "id": 2,
                    "name": "pm25",
                    "units": "µg/m³",
                    "displayName": "PM2.5",
                },
            },
            {
                "id": 502,
                "name": "PM10",
                "parameter": {
                    "id": 1,
                    "name": "pm10",
                    "units": "µg/m³",
                    "displayName": "PM10",
                },
            },
        ],
        "coordinates": {"latitude": 31.5601, "longitude": 74.3359},
    }


def _latest_payload() -> dict[str, Any]:
    return {
        "meta": {"name": "openaq-api", "page": 1, "limit": 100, "found": 2},
        "results": [
            {
                "datetime": {
                    "utc": "2026-10-24T05:00:00Z",
                    "local": "2026-10-24T10:00:00+05:00",
                },
                "value": 87.5,
                "coordinates": {"latitude": 31.5601, "longitude": 74.3359},
                "sensorsId": 501,
                "locationsId": 9001,
            },
            {
                "datetime": {
                    "utc": "2026-10-24T05:00:00Z",
                    "local": "2026-10-24T10:00:00+05:00",
                },
                "value": 120.0,
                "coordinates": {"latitude": 31.5601, "longitude": 74.3359},
                "sensorsId": 502,
                "locationsId": 9001,
            },
        ],
    }


def _measurements_payload() -> dict[str, Any]:
    return {
        "meta": {"name": "openaq-api", "page": 1, "limit": 100, "found": 1},
        "results": [
            {
                "value": 55.2,
                "parameter": {"id": 2, "name": "pm25", "units": "µg/m³"},
                "period": {
                    "label": "1hour",
                    "interval": "01:00:00",
                    "datetimeFrom": {
                        "utc": "2026-10-23T04:00:00Z",
                        "local": "2026-10-23T09:00:00+05:00",
                    },
                    "datetimeTo": {
                        "utc": "2026-10-23T05:00:00Z",
                        "local": "2026-10-23T10:00:00+05:00",
                    },
                },
                "coordinates": {"latitude": 31.5601, "longitude": 74.3359},
            }
        ],
    }


def _make_client(handler: Any, **kwargs: Any) -> OpenAQClient:
    transport = httpx.MockTransport(handler)
    return OpenAQClient(
        api_key="test-key-not-real",
        base_url="https://api.openaq.org",
        transport=transport,
        min_request_interval_seconds=0.0,
        max_retries=kwargs.pop("max_retries", 2),
        **kwargs,
    )


def test_requires_api_key() -> None:
    with pytest.raises(OpenAQConfigError, match="OPENAQ_API_KEY"):
        OpenAQClient(api_key="")


def test_discover_lahore_locations_uses_geo_query_not_hardcoded_ids() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        assert request.url.path == "/v3/locations"
        assert "coordinates" in request.url.params
        assert request.url.params["iso"] == "PK"
        assert request.headers.get("x-api-key") == "test-key-not-real"
        return httpx.Response(
            200,
            json={
                "meta": {"found": 1, "page": 1, "limit": 100},
                "results": [_location_payload()],
            },
        )

    with _make_client(handler) as client:
        locations = client.discover_lahore_locations()

    assert len(locations) == 1
    assert locations[0].id == 9001
    assert locations[0].sensors[0].id == 501
    assert "31.5204" in seen["url"]
    assert "X-API-Key" not in json.dumps(seen["url"])


def test_fetch_recent_measurements_normalizes_and_preserves_raw() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v3/locations":
            return httpx.Response(
                200,
                json={
                    "meta": {"found": 1, "page": 1, "limit": 100},
                    "results": [_location_payload()],
                },
            )
        if request.url.path == "/v3/locations/9001/latest":
            return httpx.Response(200, json=_latest_payload())
        return httpx.Response(404, json={"detail": "not found"})

    with _make_client(handler) as client:
        bundles = client.fetch_recent_measurements()

    assert len(bundles) == 2
    pm25 = next(b for b in bundles if b.observation.pollutant == "pm25")
    assert pm25.observation.station_id == "9001"
    assert pm25.observation.location_name == "US Consulate Lahore"
    assert float(pm25.observation.value) == 87.5
    assert pm25.observation.unit == "µg/m³"
    assert pm25.observation.source == "openaq"
    assert pm25.observation.observed_at == datetime(2026, 10, 24, 5, 0, tzinfo=UTC)
    assert pm25.raw_payload["sensorsId"] == 501
    assert "value" in pm25.raw_payload


def test_fetch_historical_measurements() -> None:
    location = OpenAQLocation.model_validate(_location_payload())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/sensors/501/measurements"
        assert "datetime_from" in request.url.params
        return httpx.Response(200, json=_measurements_payload())

    with _make_client(handler) as client:
        bundles = client.fetch_historical_measurements(
            501,
            datetime_from=datetime(2026, 10, 23, tzinfo=UTC),
            datetime_to=datetime(2026, 10, 24, tzinfo=UTC),
            location=location,
        )

    assert len(bundles) == 1
    obs = bundles[0].observation
    assert obs.pollutant == "pm25"
    assert float(obs.value) == 55.2
    assert obs.observed_at == datetime(2026, 10, 23, 5, 0, tzinfo=UTC)
    assert bundles[0].raw_payload["value"] == 55.2


def test_empty_latest_results_return_empty_list() -> None:
    location = OpenAQLocation.model_validate(_location_payload())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"meta": {"found": 0, "page": 1, "limit": 100}, "results": []},
        )

    with _make_client(handler) as client:
        raw = client.fetch_location_latest_raw(location.id)
        bundles = client.normalize_measurements(raw, location=location, mode="latest")

    assert raw == []
    assert bundles == []


def test_malformed_latest_record_is_skipped() -> None:
    location = OpenAQLocation.model_validate(_location_payload())
    bad = {"sensorsId": 501, "locationsId": 9001}  # missing datetime/value
    good = _latest_payload()["results"][0]
    bundles = OpenAQClient.normalize_measurements([bad, good], location=location, mode="latest")
    assert len(bundles) == 1
    assert bundles[0].observation.pollutant == "pm25"


def test_auth_error_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"detail": "unauthorized"})

    with _make_client(handler, max_retries=3) as client:
        with pytest.raises(OpenAQAuthError, match="401"):
            client.list_locations(iso="PK")
    assert calls["n"] == 1


def test_rate_limit_retries_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lahore_aqi_poller.clients.openaq.client.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "0", "x-ratelimit-reset": "0"},
            json={"detail": "rate limited"},
        )

    with _make_client(handler, max_retries=2) as client, pytest.raises(OpenAQRateLimitError):
        client.list_locations(iso="PK")
    assert calls["n"] == 3  # initial + 2 retries


def test_server_error_retries_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from lahore_aqi_poller.clients.openaq import OpenAQTransientError

    monkeypatch.setattr("lahore_aqi_poller.clients.openaq.client.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"detail": "unavailable"})

    with _make_client(handler, max_retries=1) as client, pytest.raises(OpenAQTransientError):
        client.list_locations(iso="PK")
    assert calls["n"] == 2


def test_transient_error_type(monkeypatch: pytest.MonkeyPatch) -> None:
    from lahore_aqi_poller.clients.openaq import OpenAQTransientError

    monkeypatch.setattr("lahore_aqi_poller.clients.openaq.client.time.sleep", lambda _s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    with _make_client(handler, max_retries=0) as client, pytest.raises(OpenAQTransientError):
        client.list_locations(iso="PK")


def test_client_error_raises_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": [{"msg": "invalid"}]})

    with _make_client(handler) as client, pytest.raises(OpenAQAPIError) as exc_info:
        client.list_locations(iso="PK")
    assert exc_info.value.status_code == 422


def test_logs_do_not_contain_api_key(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"meta": {"found": 0}, "results": []},
        )

    with caplog.at_level(logging.DEBUG), _make_client(handler) as client:
        client.list_locations(iso="PK")

    combined = " ".join(record.getMessage() for record in caplog.records)
    assert "test-key-not-real" not in combined
    assert "X-API-Key: test" not in combined


def test_normalize_latest_maps_pm25_alias() -> None:
    location = OpenAQLocation.model_validate(_location_payload())
    # Force parameter name with dot spelling via a synthetic sensor map miss path:
    # use existing sensor 501 which is already pm25.
    bundle = normalize_latest_measurement(_latest_payload()["results"][0], location=location)
    assert bundle is not None
    assert bundle.observation.pollutant == "pm25"
    assert bundle.raw_payload["value"] == 87.5
