"""Shared fixtures for quality-rule tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from lahore_air_quality.quality.types import AirQualityRecord, WeatherRecord


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def valid_aq(now: datetime) -> AirQualityRecord:
    return AirQualityRecord(
        station_id="PK-LHR-01",
        pollutant="pm25",
        value=Decimal("42.5"),
        unit="µg/m³",
        observed_at=now.replace(hour=11),
        source="openaq",
    )


@pytest.fixture
def valid_weather(now: datetime) -> WeatherRecord:
    return WeatherRecord(
        latitude=31.52,
        longitude=74.36,
        observed_at=now.replace(hour=11),
        temperature_c=Decimal("32"),
        relative_humidity_pct=Decimal("55"),
        precipitation_mm=Decimal("0"),
        wind_speed_ms=Decimal("3.2"),
        wind_direction_deg=Decimal("180"),
        pressure_hpa=Decimal("1008"),
        source="open-meteo",
    )
