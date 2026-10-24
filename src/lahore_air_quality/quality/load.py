"""Load real observations from PostgreSQL for quality monitoring.

Never fabricates rows. Callers must handle empty results as ``NO_DATA_AVAILABLE``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from lahore_air_quality.db.models import AirQualityObservation, WeatherObservation
from lahore_air_quality.quality.types import AirQualityRecord, WeatherRecord


def count_air_quality_rows(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(AirQualityObservation)) or 0)


def count_weather_rows(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(WeatherObservation)) or 0)


def load_air_quality_records(
    session: Session,
    *,
    observed_from: datetime | None = None,
    observed_to: datetime | None = None,
    limit: int | None = None,
) -> list[AirQualityRecord]:
    """Read normalized AQ rows from ``raw.air_quality_observations``.

    Duplicate natural keys (if any slip past constraints) are flagged
    ``is_duplicate=True`` for classification — rows are never deleted here.
    """
    stmt: Select[tuple[AirQualityObservation]] = select(AirQualityObservation).order_by(
        AirQualityObservation.observed_at.asc(),
        AirQualityObservation.station_id.asc(),
    )
    if observed_from is not None:
        stmt = stmt.where(AirQualityObservation.observed_at >= observed_from)
    if observed_to is not None:
        stmt = stmt.where(AirQualityObservation.observed_at <= observed_to)
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = list(session.scalars(stmt).all())
    key_counts = Counter((r.source, r.station_id, r.pollutant, r.observed_at) for r in rows)
    return [
        AirQualityRecord(
            station_id=r.station_id,
            pollutant=r.pollutant,
            value=r.value,
            unit=r.unit,
            observed_at=r.observed_at,
            ingested_at=r.ingested_at,
            source=r.source,
            raw_record_id=r.raw_record_id,
            is_duplicate=key_counts[(r.source, r.station_id, r.pollutant, r.observed_at)] > 1,
        )
        for r in rows
    ]


def load_weather_records(
    session: Session,
    *,
    observed_from: datetime | None = None,
    observed_to: datetime | None = None,
    limit: int | None = None,
) -> list[WeatherRecord]:
    """Read normalized weather rows from ``raw.weather_observations``."""
    stmt: Select[tuple[WeatherObservation]] = select(WeatherObservation).order_by(
        WeatherObservation.observed_at.asc()
    )
    if observed_from is not None:
        stmt = stmt.where(WeatherObservation.observed_at >= observed_from)
    if observed_to is not None:
        stmt = stmt.where(WeatherObservation.observed_at <= observed_to)
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = list(session.scalars(stmt).all())
    key_counts = Counter((r.source, r.latitude, r.longitude, r.observed_at) for r in rows)
    return [
        WeatherRecord(
            latitude=float(r.latitude) if r.latitude is not None else None,
            longitude=float(r.longitude) if r.longitude is not None else None,
            observed_at=r.observed_at,
            temperature_c=r.temperature_c,
            relative_humidity_pct=r.relative_humidity_pct,
            precipitation_mm=r.precipitation_mm,
            wind_speed_ms=r.wind_speed_ms,
            wind_direction_deg=r.wind_direction_deg,
            pressure_hpa=r.pressure_hpa,
            ingested_at=r.ingested_at,
            source=r.source,
            is_duplicate=key_counts[(r.source, r.latitude, r.longitude, r.observed_at)] > 1,
        )
        for r in rows
    ]


def weather_hours(records: Sequence[WeatherRecord]) -> list[datetime]:
    hours: list[datetime] = []
    for r in records:
        if r.observed_at is None:
            continue
        hours.append(r.observed_at.replace(minute=0, second=0, microsecond=0))
    return hours
