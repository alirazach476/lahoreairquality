"""Offline unit tests for ORM schema design (no database required)."""

from __future__ import annotations

from lahore_air_quality.db.base import Base
from lahore_air_quality.db.models import (
    AirQualityObservation,
    IngestionPayload,
    WeatherObservation,
)


def test_models_are_registered_on_metadata() -> None:
    table_keys = set(Base.metadata.tables)
    assert "raw.ingestion_payloads" in table_keys
    assert "raw.air_quality_observations" in table_keys
    assert "raw.weather_observations" in table_keys


def test_air_quality_idempotency_unique_constraint() -> None:
    table = AirQualityObservation.__table__
    unique_names = {c.name for c in table.constraints if c.name}
    assert "uq_aq_obs_source_station_pollutant_observed_at" in unique_names

    constraint = next(
        c for c in table.constraints if c.name == "uq_aq_obs_source_station_pollutant_observed_at"
    )
    cols = [col.name for col in constraint.columns]
    assert cols == ["source", "station_id", "pollutant", "observed_at"]


def test_weather_idempotency_unique_constraint() -> None:
    table = WeatherObservation.__table__
    constraint = next(
        c for c in table.constraints if c.name == "uq_weather_obs_source_lat_lon_observed_at"
    )
    cols = [col.name for col in constraint.columns]
    assert cols == ["source", "latitude", "longitude", "observed_at"]


def test_raw_payload_idempotency_unique_constraint() -> None:
    table = IngestionPayload.__table__
    constraint = next(
        c for c in table.constraints if c.name == "uq_ingestion_payloads_source_raw_record_id"
    )
    cols = [col.name for col in constraint.columns]
    assert cols == ["source", "raw_record_id"]


def test_required_air_quality_columns_present() -> None:
    cols = set(AirQualityObservation.__table__.columns.keys())
    for name in (
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
    ):
        assert name in cols


def test_required_weather_columns_present() -> None:
    cols = set(WeatherObservation.__table__.columns.keys())
    for name in (
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
    ):
        assert name in cols
