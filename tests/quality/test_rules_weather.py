"""Unit tests for weather quality rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lahore_air_quality.quality.classify import classify_weather
from lahore_air_quality.quality.rules import (
    rule_weather_duplicate,
    rule_weather_future_timestamp,
    rule_weather_missing_timestamp,
    rule_weather_range,
)
from lahore_air_quality.quality.types import QualityClass, Severity, WeatherRecord


def _wx(**kwargs) -> WeatherRecord:
    base = dict(
        latitude=31.5,
        longitude=74.3,
        observed_at=datetime(2026, 6, 15, 11, 0, tzinfo=UTC),
        temperature_c=Decimal("30"),
        relative_humidity_pct=Decimal("40"),
        precipitation_mm=Decimal("0"),
        wind_speed_ms=Decimal("2"),
        wind_direction_deg=Decimal("90"),
        pressure_hpa=Decimal("1010"),
    )
    base.update(kwargs)
    return WeatherRecord(**base)


def test_rule_weather_missing_timestamp() -> None:
    findings = rule_weather_missing_timestamp(_wx(observed_at=None))
    assert findings[0].rule_id == "missing_timestamp"
    assert findings[0].severity is Severity.INVALID


def test_rule_weather_future_timestamp(now: datetime) -> None:
    far = now + timedelta(hours=3)
    findings = rule_weather_future_timestamp(_wx(observed_at=far), now=now)
    assert findings[0].severity is Severity.INVALID


def test_rule_weather_range_out_of_bounds() -> None:
    findings = rule_weather_range(_wx(temperature_c=Decimal("99"), pressure_hpa=Decimal("500")))
    ids = {f.rule_id for f in findings}
    assert ids == {"abnormal_value"}
    assert all(f.severity is Severity.INVALID for f in findings)
    assert len(findings) == 2


def test_rule_weather_range_boundaries_ok() -> None:
    assert rule_weather_range(_wx(precipitation_mm=Decimal("500"))) == []
    assert rule_weather_range(_wx(relative_humidity_pct=Decimal("0"))) == []


def test_rule_weather_duplicate() -> None:
    findings = rule_weather_duplicate(_wx(is_duplicate=True))
    assert findings[0].severity is Severity.SUSPECT


def test_classify_weather_valid(now: datetime, valid_weather: WeatherRecord) -> None:
    result = classify_weather(valid_weather, now=now)
    assert result.quality_class is QualityClass.VALID
