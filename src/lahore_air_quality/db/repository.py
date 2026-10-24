"""Idempotent persistence helpers for raw payloads and observations.

Duplicates never delete existing raw rows. Conflicting inserts are skipped via
PostgreSQL ``ON CONFLICT DO NOTHING``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from lahore_air_quality.db.models import (
    AirQualityObservation,
    IngestionPayload,
    WeatherObservation,
)


@dataclass(frozen=True, slots=True)
class InsertResult:
    """Outcome of an idempotent insert attempt."""

    inserted: bool
    reason: str


def insert_ingestion_payload(
    session: Session,
    *,
    source: str,
    record_kind: str,
    raw_record_id: str,
    payload: dict[str, Any],
    ingested_at: datetime | None = None,
    content_hash: str | None = None,
) -> InsertResult:
    """Insert a raw payload; skip silently if ``(source, raw_record_id)`` exists."""
    values: dict[str, Any] = {
        "source": source,
        "record_kind": record_kind,
        "raw_record_id": raw_record_id,
        "payload": payload,
        "content_hash": content_hash,
    }
    if ingested_at is not None:
        values["ingested_at"] = ingested_at

    stmt = (
        insert(IngestionPayload)
        .values(**values)
        .on_conflict_do_nothing(constraint="uq_ingestion_payloads_source_raw_record_id")
        .returning(IngestionPayload.id)
    )
    row_id = session.execute(stmt).scalar_one_or_none()
    if row_id is None:
        return InsertResult(inserted=False, reason="duplicate_raw_record")
    return InsertResult(inserted=True, reason="inserted")


def insert_air_quality_observation(
    session: Session,
    *,
    source: str,
    station_id: str,
    pollutant: str,
    value: Decimal | float,
    unit: str,
    observed_at: datetime,
    raw_record_id: str,
    observation_id: str | None = None,
    location_name: str | None = None,
    latitude: Decimal | float | None = None,
    longitude: Decimal | float | None = None,
    ingested_at: datetime | None = None,
) -> InsertResult:
    """Insert a normalized AQ row; skip on natural-key conflict (never deletes raw)."""
    values: dict[str, Any] = {
        "source": source,
        "station_id": station_id,
        "pollutant": pollutant,
        "value": value,
        "unit": unit,
        "observed_at": observed_at,
        "raw_record_id": raw_record_id,
        "observation_id": observation_id,
        "location_name": location_name,
        "latitude": latitude,
        "longitude": longitude,
    }
    if ingested_at is not None:
        values["ingested_at"] = ingested_at

    stmt = (
        insert(AirQualityObservation)
        .values(**values)
        .on_conflict_do_nothing(constraint="uq_aq_obs_source_station_pollutant_observed_at")
        .returning(AirQualityObservation.id)
    )
    row_id = session.execute(stmt).scalar_one_or_none()
    if row_id is None:
        return InsertResult(inserted=False, reason="duplicate_observation")
    return InsertResult(inserted=True, reason="inserted")


def insert_weather_observation(
    session: Session,
    *,
    source: str,
    latitude: Decimal | float,
    longitude: Decimal | float,
    observed_at: datetime,
    raw_record_id: str,
    temperature_c: Decimal | float | None = None,
    relative_humidity_pct: Decimal | float | None = None,
    precipitation_mm: Decimal | float | None = None,
    wind_speed_ms: Decimal | float | None = None,
    wind_direction_deg: Decimal | float | None = None,
    pressure_hpa: Decimal | float | None = None,
    ingested_at: datetime | None = None,
) -> InsertResult:
    """Insert a normalized weather row; skip on natural-key conflict."""
    values: dict[str, Any] = {
        "source": source,
        "latitude": latitude,
        "longitude": longitude,
        "observed_at": observed_at,
        "raw_record_id": raw_record_id,
        "temperature_c": temperature_c,
        "relative_humidity_pct": relative_humidity_pct,
        "precipitation_mm": precipitation_mm,
        "wind_speed_ms": wind_speed_ms,
        "wind_direction_deg": wind_direction_deg,
        "pressure_hpa": pressure_hpa,
    }
    if ingested_at is not None:
        values["ingested_at"] = ingested_at

    stmt = (
        insert(WeatherObservation)
        .values(**values)
        .on_conflict_do_nothing(constraint="uq_weather_obs_source_lat_lon_observed_at")
        .returning(WeatherObservation.id)
    )
    row_id = session.execute(stmt).scalar_one_or_none()
    if row_id is None:
        return InsertResult(inserted=False, reason="duplicate_observation")
    return InsertResult(inserted=True, reason="inserted")
