"""Unit tests for each air-quality quality rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lahore_air_quality.quality.classify import classify_air_quality
from lahore_air_quality.quality.rules import (
    rule_abnormal_value,
    rule_duplicate_observation,
    rule_future_timestamp,
    rule_missing_timestamp,
    rule_missing_value,
    rule_negative_concentration,
    rule_unexpected_pollutant,
    rule_unexpected_unit,
)
from lahore_air_quality.quality.types import (
    AirQualityRecord,
    QualityClass,
    Severity,
)


def _aq(**kwargs) -> AirQualityRecord:
    base = dict(
        station_id="PK-1",
        pollutant="pm25",
        value=Decimal("10"),
        unit="µg/m³",
        observed_at=datetime(2026, 6, 15, 11, 0, tzinfo=UTC),
    )
    base.update(kwargs)
    return AirQualityRecord(**base)


def test_rule_missing_timestamp() -> None:
    findings = rule_missing_timestamp(_aq(observed_at=None))
    assert len(findings) == 1
    assert findings[0].rule_id == "missing_timestamp"
    assert findings[0].severity is Severity.INVALID
    assert rule_missing_timestamp(_aq()) == []


def test_rule_missing_value() -> None:
    assert rule_missing_value(_aq(value=None))[0].severity is Severity.INVALID
    assert rule_missing_value(_aq(value=Decimal("1"))) == []


def test_rule_future_timestamp_bands(now: datetime) -> None:
    assert rule_future_timestamp(_aq(observed_at=now), now=now) == []

    slight = now + timedelta(minutes=10)
    suspect = rule_future_timestamp(_aq(observed_at=slight), now=now)
    assert len(suspect) == 1
    assert suspect[0].severity is Severity.SUSPECT

    far = now + timedelta(hours=2)
    invalid = rule_future_timestamp(_aq(observed_at=far), now=now)
    assert invalid[0].severity is Severity.INVALID


def test_rule_negative_concentration() -> None:
    findings = rule_negative_concentration(_aq(value=Decimal("-0.1")))
    assert findings[0].rule_id == "negative_concentration"
    assert findings[0].severity is Severity.INVALID
    assert rule_negative_concentration(_aq(value=0)) == []


def test_rule_unexpected_pollutant() -> None:
    assert rule_unexpected_pollutant(_aq(pollutant=None))[0].severity is Severity.INVALID
    assert rule_unexpected_pollutant(_aq(pollutant="smoke"))[0].rule_id == ("unexpected_pollutant")
    assert rule_unexpected_pollutant(_aq(pollutant="pm2.5")) == []


def test_rule_unexpected_unit() -> None:
    bad = rule_unexpected_unit(_aq(unit="ppm"))  # pm25 expects µg/m³
    assert bad[0].rule_id == "unexpected_unit"
    assert bad[0].severity is Severity.INVALID
    assert rule_unexpected_unit(_aq(unit="ug/m3")) == []
    assert rule_unexpected_unit(_aq(unit=None)) == []


def test_rule_abnormal_value_suspect_and_invalid() -> None:
    suspect = rule_abnormal_value(_aq(value=Decimal("400")))
    assert suspect[0].severity is Severity.SUSPECT
    invalid = rule_abnormal_value(_aq(value=Decimal("2500")))
    assert invalid[0].severity is Severity.INVALID
    assert rule_abnormal_value(_aq(value=Decimal("50"))) == []


def test_rule_duplicate_observation() -> None:
    findings = rule_duplicate_observation(_aq(is_duplicate=True))
    assert findings[0].rule_id == "duplicate_observation"
    assert findings[0].severity is Severity.SUSPECT
    assert rule_duplicate_observation(_aq(is_duplicate=False)) == []


def test_classify_missing_weather_is_suspect(now: datetime, valid_aq: AirQualityRecord) -> None:
    result = classify_air_quality(valid_aq, now=now, has_weather_for_hour=False)
    assert result.quality_class is QualityClass.SUSPECT
    assert "missing_weather" in result.rule_ids


def test_classify_invalid_beats_suspect(now: datetime) -> None:
    record = _aq(value=Decimal("-1"), is_duplicate=True)
    result = classify_air_quality(record, now=now, has_weather_for_hour=False)
    assert result.quality_class is QualityClass.INVALID


def test_classify_valid_record(now: datetime, valid_aq: AirQualityRecord) -> None:
    result = classify_air_quality(valid_aq, now=now, has_weather_for_hour=True)
    assert result.quality_class is QualityClass.VALID
    assert result.findings == ()
