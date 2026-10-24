"""Optional live Open-Meteo API integration tests.

Not run by default. See docs/testing.md.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from lahore_air_quality.config import Settings
from lahore_aqi_poller.clients.openmeteo import OpenMeteoClient

pytestmark = pytest.mark.integration


def test_live_fetch_current_and_forecast(live_settings: Settings) -> None:
    with OpenMeteoClient.from_settings(live_settings) as client:
        current = client.fetch_current()
        forecast = client.fetch_forecast(forecast_days=1, past_days=0, include_current=False)

    assert current is not None
    assert current.observation.source == "open-meteo"
    assert current.observation.has_any_measurement()
    assert current.raw_payload
    assert isinstance(forecast, list)
    assert forecast
    assert (
        forecast[0].observation.temperature_c is not None
        or forecast[0].observation.has_any_measurement()
    )


def test_live_fetch_historical_recent_day(live_settings: Settings) -> None:
    end = date.today() - timedelta(days=5)
    start = end - timedelta(days=1)
    with OpenMeteoClient.from_settings(live_settings) as client:
        bundles = client.fetch_historical(start_date=start, end_date=end)

    assert isinstance(bundles, list)
    # Archive should return hourly rows for a full day range.
    assert len(bundles) > 0
    assert bundles[0].observation.source == "open-meteo"
    assert bundles[0].raw_payload.get("kind") == "historical_hourly"


def test_live_coordinates_come_from_settings(live_settings: Settings) -> None:
    with OpenMeteoClient.from_settings(live_settings) as client:
        assert client.coordinates.latitude == live_settings.lahore_latitude
        assert client.coordinates.longitude == live_settings.lahore_longitude
        # Smoke: datetime helper hits archive with UTC dates near "yesterday".
        end = datetime.now(tz=UTC) - timedelta(days=3)
        start = end - timedelta(days=1)
        bundles = client.fetch_historical_for_datetimes(datetime_from=start, datetime_to=end)
    assert isinstance(bundles, list)
