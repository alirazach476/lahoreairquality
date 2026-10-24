"""Production monitor must query the configured database — never fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from lahore_air_quality.db.health import DatabaseHealth
from lahore_air_quality.quality.monitor import run_data_quality_monitor
from lahore_air_quality.quality.types import AirQualityRecord, WeatherRecord


def test_monitor_returns_no_data_when_tables_empty() -> None:
    session = MagicMock()
    health = DatabaseHealth(healthy=True, message="ok", server_version="16")
    with (
        patch("lahore_air_quality.quality.monitor.count_air_quality_rows", return_value=0),
        patch("lahore_air_quality.quality.monitor.count_weather_rows", return_value=0),
        patch("lahore_air_quality.quality.monitor.load_air_quality_records") as load_aq,
        patch("lahore_air_quality.quality.monitor.load_weather_records") as load_wx,
    ):
        result = run_data_quality_monitor(session, database_health=health)
        load_aq.assert_not_called()
        load_wx.assert_not_called()

    assert result.status == "NO_DATA_AVAILABLE"
    assert "bootstrap_history" in result.message
    assert result.air_quality_report is None
    assert result.table_counts["raw.air_quality_observations"] == 0


def test_monitor_uses_loaded_db_records_not_synthetic() -> None:
    session = MagicMock()
    health = DatabaseHealth(healthy=True, message="ok", server_version="16")
    now = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    aq = [
        AirQualityRecord(
            station_id="DB-STATION-1",
            pollutant="pm25",
            value=Decimal("55"),
            unit="µg/m³",
            observed_at=now.replace(hour=10),
            source="openaq",
        )
    ]
    wx = [
        WeatherRecord(
            latitude=31.52,
            longitude=74.36,
            observed_at=now.replace(hour=10),
            temperature_c=Decimal("30"),
            source="open-meteo",
        )
    ]

    with (
        patch("lahore_air_quality.quality.monitor.count_air_quality_rows", return_value=1),
        patch("lahore_air_quality.quality.monitor.count_weather_rows", return_value=1),
        patch(
            "lahore_air_quality.quality.monitor.load_air_quality_records",
            return_value=aq,
        ) as load_aq,
        patch(
            "lahore_air_quality.quality.monitor.load_weather_records",
            return_value=wx,
        ) as load_wx,
    ):
        result = run_data_quality_monitor(session, now=now, database_health=health)
        load_aq.assert_called_once()
        load_wx.assert_called_once()
        assert load_aq.call_args.args[0] is session
        assert load_wx.call_args.args[0] is session

    assert result.status == "OK"
    assert result.air_quality_report is not None
    assert result.air_quality_report.record_counts["total"] == 1
    assert "synthetic" not in result.message.lower()
    assert any("no synthetic" in n.lower() for n in result.notes)


def test_monitor_database_unavailable() -> None:
    session = MagicMock()
    health = DatabaseHealth(healthy=False, message="connection failed")
    result = run_data_quality_monitor(session, database_health=health)
    assert result.status == "DATABASE_UNAVAILABLE"
    assert result.air_quality_report is None


def test_load_functions_query_orm_models() -> None:
    """Guard: load helpers select from real ORM tables, not fixture modules."""
    import inspect

    from lahore_air_quality.quality import load as load_mod

    source = inspect.getsource(load_mod)
    assert "AirQualityObservation" in source
    assert "WeatherObservation" in source
    assert "make_synthetic" not in source
    assert "fixtures" not in source
