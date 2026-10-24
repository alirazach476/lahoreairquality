"""Tests for report-level rules: gaps, inactivity, staleness, duplicates, report shape."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lahore_air_quality.quality.report import build_air_quality_report
from lahore_air_quality.quality.rules import (
    find_duplicate_keys,
    find_missing_intervals,
    inactive_stations,
    is_stale,
)
from lahore_air_quality.quality.thresholds import (
    EXPECTED_AQ_INTERVAL,
    GAP_FACTOR,
    SENSOR_INACTIVE_AFTER,
    STALE_AFTER,
)
from lahore_air_quality.quality.types import AirQualityRecord


def _aq(
    station: str,
    when: datetime,
    *,
    pollutant: str = "pm25",
    value: Decimal = Decimal("10"),
    is_duplicate: bool = False,
) -> AirQualityRecord:
    return AirQualityRecord(
        station_id=station,
        pollutant=pollutant,
        value=value,
        unit="µg/m³",
        observed_at=when,
        source="openaq",
        is_duplicate=is_duplicate,
    )


def test_find_duplicate_keys() -> None:
    t = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    records = [
        _aq("A", t),
        _aq("A", t),
        _aq("B", t),
    ]
    dups = find_duplicate_keys(records)
    assert len(dups) == 1
    assert dups[0][1] == "A"


def test_find_missing_intervals_sudden_gaps() -> None:
    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    stamps = [t0, t0 + timedelta(hours=1), t0 + timedelta(hours=10)]
    gaps = find_missing_intervals(stamps, expected=EXPECTED_AQ_INTERVAL, gap_factor=GAP_FACTOR)
    assert len(gaps) == 1
    assert gaps[0][2] == 9.0


def test_inactive_stations() -> None:
    now = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
    latest = {
        "active": now - timedelta(hours=1),
        "quiet": now - timedelta(hours=8),
    }
    inactive = inactive_stations(latest, now=now, inactive_after=SENSOR_INACTIVE_AFTER)
    assert inactive == ["quiet"]


def test_is_stale() -> None:
    now = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
    assert is_stale(None, now=now, stale_after=STALE_AFTER) is True
    assert is_stale(now - timedelta(hours=13), now=now, stale_after=STALE_AFTER) is True
    assert is_stale(now - timedelta(hours=1), now=now, stale_after=STALE_AFTER) is False


def test_build_air_quality_report_shape(now: datetime) -> None:
    t = now - timedelta(hours=1)
    records = [
        _aq("S1", t),
        _aq("S1", t, is_duplicate=True),
        _aq("S2", t - timedelta(hours=8), value=Decimal("-1")),
    ]
    weather_hours = [t]
    report = build_air_quality_report(records, weather_hours=weather_hours, now=now)
    data = report.as_dict()

    assert data["record_counts"]["total"] == 3
    assert "valid" in data["record_counts"]
    assert "duplicate_natural_keys" in data["duplicate_counts"]
    assert data["null_counts"]["observed_at"] == 0
    assert "stale" in data["freshness"]
    assert "inactive_stations" in data["sensor_activity"]
    assert "pm25" in data["value_extremes"]
    assert isinstance(data["missing_intervals"], list)
    assert any("never deleted" in n.lower() for n in data["notes"])
