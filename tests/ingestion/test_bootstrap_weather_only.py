"""Weather-only bootstrap: no OpenAQ key, mocked Open-Meteo only."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from ingestion.bootstrap_history.plan import build_bootstrap_plan
from ingestion.bootstrap_history.runner import execute_bootstrap
from ingestion.bootstrap_history.settings import OPEN_METEO_ATTRIBUTION, BootstrapWindow

from lahore_aqi_poller.clients.openaq.exceptions import OpenAQConfigError
from lahore_aqi_poller.clients.openmeteo.exceptions import OpenMeteoAPIError
from lahore_aqi_poller.clients.openmeteo.models import (
    NormalizedWeatherObservation,
    WeatherObservationBundle,
)


def _settings() -> MagicMock:
    settings = MagicMock()
    settings.lahore_latitude = 31.5204
    settings.lahore_longitude = 74.3587
    settings.s3_endpoint_url = "http://localhost:9000"
    settings.s3_bucket = "test"
    settings.aws_access_key_id = MagicMock()
    settings.aws_access_key_id.get_secret_value.return_value = "x"
    settings.aws_secret_access_key = MagicMock()
    settings.aws_secret_access_key.get_secret_value.return_value = "y"
    settings.aws_region = "us-east-1"
    return settings


def _window() -> BootstrapWindow:
    return BootstrapWindow(
        start=datetime(2026, 5, 1, tzinfo=UTC),
        end=datetime(2026, 5, 3, tzinfo=UTC),
    )


def test_weather_only_plan_skips_openaq_and_needs_no_key() -> None:
    """Building a weather-only plan must not construct OpenAQClient."""
    with patch(
        "ingestion.bootstrap_history.plan.OpenAQClient.from_settings",
        side_effect=OpenAQConfigError("OPENAQ_API_KEY is required"),
    ) as openaq_factory:
        plan = build_bootstrap_plan(
            settings=_settings(),
            window=_window(),
            weather_only=True,
        )
    openaq_factory.assert_not_called()
    assert plan.mode == "weather_only"
    assert plan.include_air_quality is False
    assert plan.estimated_aq_sensor_chunks == 0
    assert "raw.weather_observations" in plan.target_tables
    assert "raw.air_quality_observations" not in plan.target_tables
    assert plan.data_provenance["weather"] == "open_meteo_model_historical"
    assert plan.data_provenance["air_quality"] == "skipped"
    assert any("Open-Meteo.com" in a for a in plan.attribution)
    assert OPEN_METEO_ATTRIBUTION in plan.attribution
    # Must not claim ground-station weather
    assert "not in-situ" in plan.as_dict()["weather_coordinates"]["provenance"]


def test_full_plan_still_requires_openaq_when_key_missing() -> None:
    with (
        patch(
            "ingestion.bootstrap_history.plan.OpenAQClient.from_settings",
            side_effect=OpenAQConfigError("OPENAQ_API_KEY is required"),
        ),
        pytest.raises(OpenAQConfigError, match="OPENAQ_API_KEY"),
    ):
        build_bootstrap_plan(
            settings=_settings(),
            window=_window(),
            weather_only=False,
        )


def test_execute_weather_only_does_not_open_openaq() -> None:
    plan = build_bootstrap_plan(
        settings=_settings(),
        window=_window(),
        weather_only=True,
    )
    meteo = MagicMock()
    obs = NormalizedWeatherObservation(
        observed_at=datetime(2026, 5, 1, 12, tzinfo=UTC),
        latitude=31.52,
        longitude=74.36,
        temperature_c=30.0,
        relative_humidity_pct=40.0,
        precipitation_mm=0.0,
        wind_speed_ms=2.0,
        wind_direction_deg=90.0,
        pressure_hpa=1010.0,
        source="open-meteo",
        raw_record_id="wx-1",
    )
    meteo.fetch_historical.return_value = [
        WeatherObservationBundle(observation=obs, raw_payload={"hourly": {}})
    ]

    processor = MagicMock()
    processor.process.return_value = MagicMock(
        status="processed", event_id="wx-1", detail=None, failed_stage=None
    )

    with (
        patch(
            "ingestion.bootstrap_history.runner.build_event_processor",
            return_value=(processor, "postgres_only"),
        ),
        patch(
            "ingestion.bootstrap_history.runner.OpenAQClient.from_settings",
            side_effect=AssertionError("OpenAQ must not be used in weather_only"),
        ) as openaq_factory,
        patch(
            "ingestion.bootstrap_history.runner.persist_event",
        ) as persist,
    ):
        result = execute_bootstrap(
            plan,
            session_factory=MagicMock(),
            settings=_settings(),
            openmeteo_client=meteo,
        )

    openaq_factory.assert_not_called()
    meteo.fetch_historical.assert_called_once()
    assert result.weather_observations_fetched == 1
    assert result.aq_observations_fetched == 0
    assert persist.call_count == 1
    assert any("not ground-station" in n for n in result.notes)


def test_execute_weather_only_api_error() -> None:
    plan = build_bootstrap_plan(settings=_settings(), window=_window(), weather_only=True)
    meteo = MagicMock()
    meteo.fetch_historical.side_effect = OpenMeteoAPIError("upstream failed")

    with patch(
        "ingestion.bootstrap_history.runner.build_event_processor",
        return_value=(MagicMock(), "postgres_only"),
    ):
        result = execute_bootstrap(
            plan,
            session_factory=MagicMock(),
            settings=_settings(),
            openmeteo_client=meteo,
        )

    assert result.weather_observations_fetched == 0
    assert any("OpenMeteoAPIError" in e for e in result.errors)


def test_execute_weather_only_empty_response() -> None:
    plan = build_bootstrap_plan(settings=_settings(), window=_window(), weather_only=True)
    meteo = MagicMock()
    meteo.fetch_historical.return_value = []

    with patch(
        "ingestion.bootstrap_history.runner.build_event_processor",
        return_value=(MagicMock(), "postgres_only"),
    ):
        result = execute_bootstrap(
            plan,
            session_factory=MagicMock(),
            settings=_settings(),
            openmeteo_client=meteo,
        )

    assert result.weather_observations_fetched == 0
    assert any("empty response" in e for e in result.errors)
