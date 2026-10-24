"""Tests for SQLAlchemy model metadata and basic persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from lahore_air_quality.db.health import check_database_health
from lahore_air_quality.db.models import (
    AirQualityObservation,
    IngestionPayload,
    WeatherObservation,
)
from lahore_air_quality.db.models.raw_payload import RecordKind

pytestmark = pytest.mark.postgres


def test_health_check_reports_healthy(postgres_engine: Engine) -> None:
    result = check_database_health(postgres_engine)
    assert result.healthy is True
    assert result.server_version is not None
    assert "password" not in result.message.lower()


def test_raw_tables_exist_with_expected_columns(
    postgres_engine: Engine, migrated_schema: None
) -> None:
    inspector = inspect(postgres_engine)
    tables = set(inspector.get_table_names(schema="raw"))
    assert "ingestion_payloads" in tables
    assert "air_quality_observations" in tables
    assert "weather_observations" in tables

    aq_cols = {
        col["name"] for col in inspector.get_columns("air_quality_observations", schema="raw")
    }
    expected_aq = {
        "id",
        "observation_id",
        "station_id",
        "location_name",
        "latitude",
        "longitude",
        "pollutant",
        "value",
        "unit",
        "observed_at",
        "ingested_at",
        "source",
        "raw_record_id",
    }
    assert expected_aq.issubset(aq_cols)

    weather_cols = {
        col["name"] for col in inspector.get_columns("weather_observations", schema="raw")
    }
    expected_weather = {
        "observed_at",
        "latitude",
        "longitude",
        "temperature_c",
        "relative_humidity_pct",
        "precipitation_mm",
        "wind_speed_ms",
        "wind_direction_deg",
        "pressure_hpa",
        "source",
        "ingested_at",
        "raw_record_id",
    }
    assert expected_weather.issubset(weather_cols)


def test_unique_constraints_defined(postgres_engine: Engine, migrated_schema: None) -> None:
    inspector = inspect(postgres_engine)
    aq_uniques = inspector.get_unique_constraints("air_quality_observations", schema="raw")
    aq_names = {u["name"] for u in aq_uniques}
    assert "uq_aq_obs_source_station_pollutant_observed_at" in aq_names

    weather_uniques = inspector.get_unique_constraints("weather_observations", schema="raw")
    weather_names = {u["name"] for u in weather_uniques}
    assert "uq_weather_obs_source_lat_lon_observed_at" in weather_names

    raw_uniques = inspector.get_unique_constraints("ingestion_payloads", schema="raw")
    raw_names = {u["name"] for u in raw_uniques}
    assert "uq_ingestion_payloads_source_raw_record_id" in raw_names


def test_can_insert_air_quality_and_weather_rows(
    postgres_engine: Engine, migrated_schema: None
) -> None:
    observed_at = datetime(2026, 10, 24, 5, 0, 0, tzinfo=UTC)
    with Session(postgres_engine) as session:
        session.add(
            IngestionPayload(
                source="test",
                record_kind=RecordKind.AIR_QUALITY.value,
                raw_record_id="raw-aq-1",
                payload={"pollutant": "pm25", "value": 42},
            )
        )
        session.add(
            AirQualityObservation(
                observation_id="obs-1",
                station_id="lahore-station-1",
                location_name="Lahore",
                latitude=Decimal("31.520400"),
                longitude=Decimal("74.358700"),
                pollutant="pm25",
                value=Decimal("42.500000"),
                unit="µg/m³",
                observed_at=observed_at,
                source="test",
                raw_record_id="raw-aq-1",
            )
        )
        session.add(
            WeatherObservation(
                observed_at=observed_at,
                latitude=Decimal("31.520400"),
                longitude=Decimal("74.358700"),
                temperature_c=Decimal("28.50"),
                relative_humidity_pct=Decimal("55.00"),
                precipitation_mm=Decimal("0.000"),
                wind_speed_ms=Decimal("3.200"),
                wind_direction_deg=Decimal("180.00"),
                pressure_hpa=Decimal("1008.25"),
                source="test",
                raw_record_id="raw-wx-1",
            )
        )
        session.commit()

        aq = session.scalar(
            select(AirQualityObservation).where(AirQualityObservation.raw_record_id == "raw-aq-1")
        )
        weather = session.scalar(
            select(WeatherObservation).where(WeatherObservation.raw_record_id == "raw-wx-1")
        )
        assert aq is not None
        assert aq.pollutant == "pm25"
        assert weather is not None
        assert weather.temperature_c == Decimal("28.50")
