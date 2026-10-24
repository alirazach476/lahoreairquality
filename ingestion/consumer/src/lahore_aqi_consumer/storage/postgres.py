"""Idempotent PostgreSQL writes for normalized observations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from lahore_air_quality.db.repository import (
    InsertResult,
    insert_air_quality_observation,
    insert_ingestion_payload,
    insert_weather_observation,
)
from lahore_aqi_consumer.schema import IngestionEventEnvelope

logger = logging.getLogger(__name__)


class PostgresWriteError(Exception):
    """Raised when a database write fails (retryable by default)."""


class PermanentPostgresWriteError(PostgresWriteError):
    """Non-retryable payload/shape error — commit offset after reject, do not spin."""


@dataclass(frozen=True, slots=True)
class PostgresWriteResult:
    payload: InsertResult
    observation: InsertResult

    @property
    def is_duplicate(self) -> bool:
        return (not self.payload.inserted) and (not self.observation.inserted)


class PostgresObservationWriter:
    """Persist envelope raw + normalized rows using existing repository helpers."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def write(self, envelope: IngestionEventEnvelope) -> PostgresWriteResult:
        session = self._session_factory()
        try:
            payload_result = insert_ingestion_payload(
                session,
                source=envelope.source,
                record_kind=envelope.record_kind,
                raw_record_id=envelope.event_id,
                payload={
                    "envelope_raw": envelope.raw,
                    "event_id": envelope.event_id,
                    "idempotency_key": envelope.idempotency_key,
                },
                ingested_at=envelope.ingested_at,
            )
            if envelope.record_kind == "air_quality":
                observation_result = self._insert_air_quality(session, envelope)
            else:
                observation_result = self._insert_weather(session, envelope)
            session.commit()
            result = PostgresWriteResult(payload=payload_result, observation=observation_result)
            logger.info(
                "postgres_write_ok",
                extra={
                    "event_id": envelope.event_id,
                    "payload_inserted": payload_result.inserted,
                    "observation_inserted": observation_result.inserted,
                    "duplicate": result.is_duplicate,
                },
            )
            return result
        except PermanentPostgresWriteError:
            session.rollback()
            raise
        except PostgresWriteError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            logger.exception(
                "postgres_write_failed",
                extra={
                    "event_id": envelope.event_id,
                    "error_type": type(exc).__name__,
                },
            )
            raise PostgresWriteError(
                f"PostgreSQL write failed for {envelope.event_id}: {type(exc).__name__}"
            ) from exc
        finally:
            session.close()

    def _insert_air_quality(
        self, session: Session, envelope: IngestionEventEnvelope
    ) -> InsertResult:
        n = envelope.normalized
        try:
            return insert_air_quality_observation(
                session,
                source=str(n.get("source") or envelope.source),
                station_id=str(n["station_id"]),
                pollutant=str(n["pollutant"]),
                value=_as_number(n["value"]),
                unit=str(n["unit"]),
                observed_at=_as_datetime(n.get("observed_at"), envelope.event_timestamp),
                raw_record_id=str(n.get("raw_record_id") or envelope.event_id),
                observation_id=_optional_str(n.get("observation_id")),
                location_name=_optional_str(n.get("location_name")),
                latitude=_optional_number(n.get("latitude")),
                longitude=_optional_number(n.get("longitude")),
                ingested_at=envelope.ingested_at,
            )
        except KeyError as exc:
            raise PermanentPostgresWriteError(
                f"air_quality normalized payload missing field {exc}"
            ) from exc
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise PermanentPostgresWriteError(
                f"air_quality normalized payload invalid: {type(exc).__name__}: {exc}"
            ) from exc

    def _insert_weather(self, session: Session, envelope: IngestionEventEnvelope) -> InsertResult:
        n = envelope.normalized
        try:
            return insert_weather_observation(
                session,
                source=str(n.get("source") or envelope.source),
                latitude=_as_number(n["latitude"]),
                longitude=_as_number(n["longitude"]),
                observed_at=_as_datetime(n.get("observed_at"), envelope.event_timestamp),
                raw_record_id=str(n.get("raw_record_id") or envelope.event_id),
                temperature_c=_optional_number(n.get("temperature_c")),
                relative_humidity_pct=_optional_number(n.get("relative_humidity_pct")),
                precipitation_mm=_optional_number(n.get("precipitation_mm")),
                wind_speed_ms=_optional_number(n.get("wind_speed_ms")),
                wind_direction_deg=_optional_number(n.get("wind_direction_deg")),
                pressure_hpa=_optional_number(n.get("pressure_hpa")),
                ingested_at=envelope.ingested_at,
            )
        except KeyError as exc:
            raise PermanentPostgresWriteError(
                f"weather normalized payload missing field {exc}"
            ) from exc
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise PermanentPostgresWriteError(
                f"weather normalized payload invalid: {type(exc).__name__}: {exc}"
            ) from exc


def _as_number(value: Any) -> Decimal:
    return Decimal(str(value))


def _optional_number(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_datetime(value: Any, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)
