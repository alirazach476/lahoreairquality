"""Convert Open-Meteo responses into internal weather observations."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from lahore_aqi_poller.clients.openmeteo.constants import SOURCE_NAME
from lahore_aqi_poller.clients.openmeteo.models import (
    CurrentWeather,
    NormalizedWeatherObservation,
    OpenMeteoResponse,
    WeatherObservationBundle,
)

logger = logging.getLogger(__name__)


def _parse_openmeteo_time(value: str) -> datetime:
    """Parse Open-Meteo time strings (``YYYY-MM-DDTHH:MM`` or with offset/Z)."""
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _as_optional_decimal(value: float | int | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        msg = f"invalid numeric value: {value!r}"
        raise ValueError(msg) from exc


def build_raw_record_id(
    *,
    latitude: float,
    longitude: float,
    observed_at: datetime,
    kind: str,
) -> str:
    """Stable raw record id for idempotent archival."""
    stamp = observed_at.astimezone(UTC).isoformat()
    material = f"{SOURCE_NAME}|{latitude:.6f}|{longitude:.6f}|{stamp}|{kind}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return f"openmeteo:{kind}:{digest}"


def _response_meta(parsed: OpenMeteoResponse) -> dict[str, Any]:
    return {
        "latitude": parsed.latitude,
        "longitude": parsed.longitude,
        "timezone": parsed.timezone,
        "elevation": parsed.elevation,
        "utc_offset_seconds": parsed.utc_offset_seconds,
        "hourly_units": parsed.hourly_units,
        "current_units": parsed.current_units,
    }


def normalize_current(
    raw_response: dict[str, Any],
    *,
    request_latitude: float,
    request_longitude: float,
) -> WeatherObservationBundle | None:
    """Normalize the Forecast API ``current`` block.

    Returns ``None`` when current weather is missing or unusable.
    """
    try:
        parsed = OpenMeteoResponse.model_validate(raw_response)
    except Exception:
        logger.exception("Malformed Open-Meteo response while normalizing current weather")
        return None

    if parsed.current is None:
        logger.info("Open-Meteo response has no current weather block")
        return None

    return _bundle_from_current(
        parsed.current,
        resolved_latitude=parsed.latitude,
        resolved_longitude=parsed.longitude,
        request_latitude=request_latitude,
        request_longitude=request_longitude,
        response_meta=_response_meta(parsed),
        raw_current=dict(raw_response.get("current") or {}),
    )


def _bundle_from_current(
    current: CurrentWeather,
    *,
    resolved_latitude: float,
    resolved_longitude: float,
    request_latitude: float,
    request_longitude: float,
    response_meta: dict[str, Any],
    raw_current: dict[str, Any],
) -> WeatherObservationBundle | None:
    try:
        observed_at = _parse_openmeteo_time(current.time)
        observation = NormalizedWeatherObservation(
            observed_at=observed_at,
            latitude=Decimal(f"{resolved_latitude:.6f}"),
            longitude=Decimal(f"{resolved_longitude:.6f}"),
            temperature_c=_as_optional_decimal(current.temperature_2m),
            relative_humidity_pct=_as_optional_decimal(current.relative_humidity_2m),
            precipitation_mm=_as_optional_decimal(current.precipitation),
            wind_speed_ms=_as_optional_decimal(current.wind_speed_10m),
            wind_direction_deg=_as_optional_decimal(current.wind_direction_10m),
            pressure_hpa=_as_optional_decimal(current.surface_pressure),
            source=SOURCE_NAME,
            raw_record_id=build_raw_record_id(
                latitude=request_latitude,
                longitude=request_longitude,
                observed_at=observed_at,
                kind="current",
            ),
        )
        if not observation.has_any_measurement():
            logger.warning(
                "Skipping current weather at %s: all requested variables are null",
                observed_at.isoformat(),
            )
            return None

        raw_payload = {
            "kind": "current",
            "request_latitude": request_latitude,
            "request_longitude": request_longitude,
            "resolved_latitude": resolved_latitude,
            "resolved_longitude": resolved_longitude,
            "current": raw_current,
        }
        return WeatherObservationBundle(
            observation=observation,
            raw_payload=raw_payload,
            response_meta=response_meta,
        )
    except Exception:
        logger.exception("Failed to normalize Open-Meteo current weather; skipping")
        return None


def normalize_hourly(
    raw_response: dict[str, Any],
    *,
    request_latitude: float,
    request_longitude: float,
    kind: str = "hourly",
) -> list[WeatherObservationBundle]:
    """Normalize Open-Meteo ``hourly`` arrays into observation bundles.

    Missing individual variable values become ``None``. Timesteps where every
    requested variable is null are skipped. Malformed responses yield an empty
    list after logging.
    """
    try:
        parsed = OpenMeteoResponse.model_validate(raw_response)
    except Exception:
        logger.exception("Malformed Open-Meteo response while normalizing hourly weather")
        return []

    hourly = parsed.hourly
    if hourly is None or not hourly.time:
        logger.info("Open-Meteo response has empty hourly series (kind=%s)", kind)
        return []

    meta = _response_meta(parsed)
    bundles: list[WeatherObservationBundle] = []
    n = len(hourly.time)

    for index in range(n):
        try:
            time_raw = hourly.time[index]
            observed_at = _parse_openmeteo_time(time_raw)

            def _at(series: list[float | None] | None, i: int = index) -> float | None:
                if series is None or i >= len(series):
                    return None
                return series[i]

            temperature = _at(hourly.temperature_2m)
            humidity = _at(hourly.relative_humidity_2m)
            precip = _at(hourly.precipitation)
            wind_speed = _at(hourly.wind_speed_10m)
            wind_dir = _at(hourly.wind_direction_10m)
            pressure = _at(hourly.surface_pressure)

            observation = NormalizedWeatherObservation(
                observed_at=observed_at,
                latitude=Decimal(f"{parsed.latitude:.6f}"),
                longitude=Decimal(f"{parsed.longitude:.6f}"),
                temperature_c=_as_optional_decimal(temperature),
                relative_humidity_pct=_as_optional_decimal(humidity),
                precipitation_mm=_as_optional_decimal(precip),
                wind_speed_ms=_as_optional_decimal(wind_speed),
                wind_direction_deg=_as_optional_decimal(wind_dir),
                pressure_hpa=_as_optional_decimal(pressure),
                source=SOURCE_NAME,
                raw_record_id=build_raw_record_id(
                    latitude=request_latitude,
                    longitude=request_longitude,
                    observed_at=observed_at,
                    kind=kind,
                ),
            )
            if not observation.has_any_measurement():
                logger.debug(
                    "Skipping hourly timestep %s: all variables null",
                    observed_at.isoformat(),
                )
                continue

            raw_payload = {
                "kind": kind,
                "request_latitude": request_latitude,
                "request_longitude": request_longitude,
                "resolved_latitude": parsed.latitude,
                "resolved_longitude": parsed.longitude,
                "time": time_raw,
                "temperature_2m": temperature,
                "relative_humidity_2m": humidity,
                "precipitation": precip,
                "wind_speed_10m": wind_speed,
                "wind_direction_10m": wind_dir,
                "surface_pressure": pressure,
                "hourly_units": parsed.hourly_units,
            }
            bundles.append(
                WeatherObservationBundle(
                    observation=observation,
                    raw_payload=raw_payload,
                    response_meta=meta,
                )
            )
        except Exception:
            logger.exception(
                "Skipping malformed Open-Meteo hourly index=%s kind=%s",
                index,
                kind,
            )
            continue

    logger.info(
        "Normalized %s/%s hourly weather timesteps (kind=%s)",
        len(bundles),
        n,
        kind,
    )
    return bundles
