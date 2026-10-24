"""Convert OpenAQ v3 payloads into internal normalized observations."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from lahore_aqi_poller.clients.openaq.constants import SOURCE_NAME
from lahore_aqi_poller.clients.openaq.models import (
    LatestMeasurement,
    NormalizedAirQualityObservation,
    ObservationBundle,
    OpenAQLocation,
    SensorBase,
    SensorMeasurement,
)

logger = logging.getLogger(__name__)


def _parse_utc(value: str) -> datetime:
    """Parse an OpenAQ UTC timestamp into an aware datetime."""
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    return datetime.fromisoformat(cleaned)


def _as_decimal(value: float | int | str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        msg = f"invalid numeric value: {value!r}"
        raise ValueError(msg) from exc


def _coords_decimals(
    latitude: float | None, longitude: float | None
) -> tuple[Decimal | None, Decimal | None]:
    lat = Decimal(str(latitude)) if latitude is not None else None
    lon = Decimal(str(longitude)) if longitude is not None else None
    return lat, lon


def build_raw_record_id(*, sensor_id: int, pollutant: str, observed_at: datetime) -> str:
    """Stable idempotency-friendly raw record id derived from measurement identity."""
    stamp = observed_at.astimezone(UTC).isoformat()
    material = f"{SOURCE_NAME}|{sensor_id}|{pollutant}|{stamp}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return f"openaq:{sensor_id}:{digest}"


def normalize_latest_measurement(
    raw: dict[str, Any],
    *,
    location: OpenAQLocation,
    sensor: SensorBase | None = None,
) -> ObservationBundle | None:
    """Normalize a ``/locations/{id}/latest`` row.

    Returns ``None`` when the record is malformed (logged, not raised).
    """
    try:
        latest = LatestMeasurement.model_validate(raw)
        resolved_sensor = sensor or location.sensor_by_id.get(latest.sensors_id)
        if resolved_sensor is None:
            logger.warning(
                "Skipping latest measurement: unknown sensorsId=%s at location_id=%s",
                latest.sensors_id,
                location.id,
            )
            return None

        observed_at = _parse_utc(latest.datetime.utc)
        pollutant = resolved_sensor.parameter.name
        unit = resolved_sensor.parameter.units
        value = _as_decimal(latest.value)

        lat_src = (
            latest.coordinates.latitude
            if latest.coordinates and latest.coordinates.latitude is not None
            else (location.coordinates.latitude if location.coordinates else None)
        )
        lon_src = (
            latest.coordinates.longitude
            if latest.coordinates and latest.coordinates.longitude is not None
            else (location.coordinates.longitude if location.coordinates else None)
        )
        latitude, longitude = _coords_decimals(lat_src, lon_src)

        observation = NormalizedAirQualityObservation(
            observation_id=f"latest:{location.id}:{latest.sensors_id}:{observed_at.isoformat()}",
            station_id=str(location.id),
            location_name=location.name,
            latitude=latitude,
            longitude=longitude,
            pollutant=pollutant,
            value=value,
            unit=unit,
            observed_at=observed_at,
            source=SOURCE_NAME,
            raw_record_id=build_raw_record_id(
                sensor_id=latest.sensors_id,
                pollutant=pollutant,
                observed_at=observed_at,
            ),
        )
        return ObservationBundle(
            observation=observation,
            raw_payload=dict(raw),
            location=location,
        )
    except Exception:
        logger.exception(
            "Malformed OpenAQ latest measurement at location_id=%s; skipping record",
            location.id,
        )
        return None


def normalize_sensor_measurement(
    raw: dict[str, Any],
    *,
    sensor_id: int,
    location: OpenAQLocation | None = None,
    fallback_parameter_name: str | None = None,
    fallback_unit: str | None = None,
) -> ObservationBundle | None:
    """Normalize a ``/sensors/{id}/measurements`` row.

    Returns ``None`` when the record is malformed (logged, not raised).
    """
    try:
        measurement = SensorMeasurement.model_validate(raw)
        if measurement.value is None:
            logger.warning("Skipping sensor measurement with null value sensor_id=%s", sensor_id)
            return None

        parameter = measurement.parameter
        pollutant = parameter.name if parameter is not None else fallback_parameter_name
        unit = parameter.units if parameter is not None else fallback_unit
        if not pollutant or not unit:
            logger.warning(
                "Skipping sensor measurement missing parameter/unit sensor_id=%s",
                sensor_id,
            )
            return None

        observed_raw: str | None = None
        if measurement.period and measurement.period.datetime_to:
            observed_raw = measurement.period.datetime_to.utc
        elif measurement.period and measurement.period.datetime_from:
            observed_raw = measurement.period.datetime_from.utc
        if not observed_raw:
            logger.warning(
                "Skipping sensor measurement missing period datetime sensor_id=%s",
                sensor_id,
            )
            return None

        observed_at = _parse_utc(observed_raw)
        value = _as_decimal(measurement.value)

        lat_src = (
            measurement.coordinates.latitude
            if measurement.coordinates
            else (location.coordinates.latitude if location and location.coordinates else None)
        )
        lon_src = (
            measurement.coordinates.longitude
            if measurement.coordinates
            else (location.coordinates.longitude if location and location.coordinates else None)
        )
        latitude, longitude = _coords_decimals(lat_src, lon_src)

        observation = NormalizedAirQualityObservation(
            observation_id=f"meas:{sensor_id}:{observed_at.isoformat()}",
            station_id=str(location.id) if location is not None else str(sensor_id),
            location_name=location.name if location is not None else None,
            latitude=latitude,
            longitude=longitude,
            pollutant=pollutant,
            value=value,
            unit=unit,
            observed_at=observed_at,
            source=SOURCE_NAME,
            raw_record_id=build_raw_record_id(
                sensor_id=sensor_id,
                pollutant=pollutant,
                observed_at=observed_at,
            ),
        )
        return ObservationBundle(
            observation=observation,
            raw_payload=dict(raw),
            location=location,
        )
    except Exception:
        logger.exception(
            "Malformed OpenAQ sensor measurement sensor_id=%s; skipping record",
            sensor_id,
        )
        return None


def normalize_latest_results(
    results: list[dict[str, Any]],
    *,
    location: OpenAQLocation,
) -> list[ObservationBundle]:
    """Normalize a list of latest rows, skipping invalid entries."""
    if not results:
        logger.info("Empty latest measurement results for location_id=%s", location.id)
        return []

    bundles: list[ObservationBundle] = []
    for raw in results:
        if not isinstance(raw, dict):
            logger.warning("Skipping non-object latest result at location_id=%s", location.id)
            continue
        bundle = normalize_latest_measurement(raw, location=location)
        if bundle is not None:
            bundles.append(bundle)

    logger.info(
        "Normalized %s/%s latest measurements for location_id=%s",
        len(bundles),
        len(results),
        location.id,
    )
    return bundles


def normalize_sensor_results(
    results: list[dict[str, Any]],
    *,
    sensor_id: int,
    location: OpenAQLocation | None = None,
    fallback_parameter_name: str | None = None,
    fallback_unit: str | None = None,
) -> list[ObservationBundle]:
    """Normalize historical sensor measurement rows, skipping invalid entries."""
    if not results:
        logger.info("Empty measurement results for sensor_id=%s", sensor_id)
        return []

    bundles: list[ObservationBundle] = []
    for raw in results:
        if not isinstance(raw, dict):
            logger.warning("Skipping non-object measurement for sensor_id=%s", sensor_id)
            continue
        bundle = normalize_sensor_measurement(
            raw,
            sensor_id=sensor_id,
            location=location,
            fallback_parameter_name=fallback_parameter_name,
            fallback_unit=fallback_unit,
        )
        if bundle is not None:
            bundles.append(bundle)

    logger.info(
        "Normalized %s/%s historical measurements for sensor_id=%s",
        len(bundles),
        len(results),
        sensor_id,
    )
    return bundles
