"""Idempotency / duplicate-handling behaviour for the persistence layer."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lahore_air_quality.db.models import (
    AirQualityObservation,
    IngestionPayload,
    WeatherObservation,
)
from lahore_air_quality.db.models.raw_payload import RecordKind
from lahore_air_quality.db.repository import (
    insert_air_quality_observation,
    insert_ingestion_payload,
    insert_weather_observation,
)

pytestmark = pytest.mark.postgres

OBSERVED_AT = datetime(2026, 10, 24, 6, 30, 0, tzinfo=UTC)


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_duplicate_raw_payload_is_skipped_not_deleted(
    postgres_engine: Engine, migrated_schema: None
) -> None:
    with Session(postgres_engine) as session:
        first = insert_ingestion_payload(
            session,
            source="openaq",
            record_kind=RecordKind.AIR_QUALITY.value,
            raw_record_id="dup-raw-1",
            payload={"v": 1},
        )
        second = insert_ingestion_payload(
            session,
            source="openaq",
            record_kind=RecordKind.AIR_QUALITY.value,
            raw_record_id="dup-raw-1",
            payload={"v": 2},
        )
        session.commit()

        assert first.inserted is True
        assert second.inserted is False
        assert second.reason == "duplicate_raw_record"
        assert _count(session, IngestionPayload) == 1

        # Original payload retained (not overwritten / deleted).
        row = session.scalar(
            select(IngestionPayload).where(IngestionPayload.raw_record_id == "dup-raw-1")
        )
        assert row is not None
        assert row.payload == {"v": 1}


def test_duplicate_air_quality_natural_key_is_skipped(
    postgres_engine: Engine, migrated_schema: None
) -> None:
    with Session(postgres_engine) as session:
        insert_ingestion_payload(
            session,
            source="openaq",
            record_kind=RecordKind.AIR_QUALITY.value,
            raw_record_id="aq-raw-a",
            payload={"pm25": 10},
        )
        first = insert_air_quality_observation(
            session,
            source="openaq",
            station_id="PK-LHE-1",
            pollutant="pm25",
            value=Decimal("10.0"),
            unit="µg/m³",
            observed_at=OBSERVED_AT,
            raw_record_id="aq-raw-a",
        )
        # Replay with a *new* raw id still must not create a second observation
        # for the same natural key; raw can be stored separately.
        insert_ingestion_payload(
            session,
            source="openaq",
            record_kind=RecordKind.AIR_QUALITY.value,
            raw_record_id="aq-raw-b",
            payload={"pm25": 10, "replay": True},
        )
        second = insert_air_quality_observation(
            session,
            source="openaq",
            station_id="PK-LHE-1",
            pollutant="pm25",
            value=Decimal("99.0"),
            unit="µg/m³",
            observed_at=OBSERVED_AT,
            raw_record_id="aq-raw-b",
        )
        session.commit()

        assert first.inserted is True
        assert second.inserted is False
        assert _count(session, AirQualityObservation) == 1
        assert _count(session, IngestionPayload) == 2

        obs = session.scalar(select(AirQualityObservation))
        assert obs is not None
        assert obs.value == Decimal("10.000000")
        assert obs.raw_record_id == "aq-raw-a"


def test_orm_unique_constraint_raises_without_on_conflict(
    postgres_engine: Engine, migrated_schema: None
) -> None:
    with Session(postgres_engine) as session:
        session.add(
            AirQualityObservation(
                station_id="PK-LHE-2",
                pollutant="pm10",
                value=Decimal("20"),
                unit="µg/m³",
                observed_at=OBSERVED_AT,
                source="openaq",
                raw_record_id="orm-1",
            )
        )
        session.commit()

    with Session(postgres_engine) as session:
        session.add(
            AirQualityObservation(
                station_id="PK-LHE-2",
                pollutant="pm10",
                value=Decimal("21"),
                unit="µg/m³",
                observed_at=OBSERVED_AT,
                source="openaq",
                raw_record_id="orm-2",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_duplicate_weather_natural_key_is_skipped(
    postgres_engine: Engine, migrated_schema: None
) -> None:
    lat = Decimal("31.520400")
    lon = Decimal("74.358700")
    with Session(postgres_engine) as session:
        first = insert_weather_observation(
            session,
            source="open-meteo",
            latitude=lat,
            longitude=lon,
            observed_at=OBSERVED_AT,
            raw_record_id="wx-1",
            temperature_c=Decimal("30.0"),
        )
        second = insert_weather_observation(
            session,
            source="open-meteo",
            latitude=lat,
            longitude=lon,
            observed_at=OBSERVED_AT,
            raw_record_id="wx-2",
            temperature_c=Decimal("31.0"),
        )
        session.commit()

        assert first.inserted is True
        assert second.inserted is False
        assert _count(session, WeatherObservation) == 1
        row = session.scalar(select(WeatherObservation))
        assert row is not None
        assert row.temperature_c == Decimal("30.00")
        assert row.raw_record_id == "wx-1"
