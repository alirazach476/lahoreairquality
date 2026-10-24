"""Pydantic models for Open-Meteo payloads and normalized weather observations."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Ignore unknown Open-Meteo fields for forward compatibility."""

    model_config = ConfigDict(extra="ignore")


class GeoPoint(StrictModel):
    """Configurable geographic target (typically Lahore from settings)."""

    latitude: float
    longitude: float

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, value: float) -> float:
        if not -90.0 <= value <= 90.0:
            msg = "latitude must be between -90 and 90"
            raise ValueError(msg)
        return value

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, value: float) -> float:
        if not -180.0 <= value <= 180.0:
            msg = "longitude must be between -180 and 180"
            raise ValueError(msg)
        return value


class HourlySeries(StrictModel):
    """Open-Meteo ``hourly`` object (parallel arrays keyed by variable name)."""

    time: list[str] = Field(default_factory=list)
    temperature_2m: list[float | None] | None = None
    relative_humidity_2m: list[float | None] | None = None
    precipitation: list[float | None] | None = None
    wind_speed_10m: list[float | None] | None = None
    wind_direction_10m: list[float | None] | None = None
    surface_pressure: list[float | None] | None = None

    @model_validator(mode="after")
    def validate_parallel_lengths(self) -> HourlySeries:
        expected = len(self.time)
        for name in (
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "wind_speed_10m",
            "wind_direction_10m",
            "surface_pressure",
        ):
            series = getattr(self, name)
            if series is not None and len(series) != expected:
                msg = f"hourly.{name} length {len(series)} != time length {expected}"
                raise ValueError(msg)
        return self


class CurrentWeather(StrictModel):
    """Open-Meteo ``current`` object from the Forecast API."""

    time: str
    temperature_2m: float | None = None
    relative_humidity_2m: float | None = None
    precipitation: float | None = None
    wind_speed_10m: float | None = None
    wind_direction_10m: float | None = None
    surface_pressure: float | None = None
    interval: int | None = None


class OpenMeteoResponse(StrictModel):
    """Subset of the Open-Meteo forecast/archive JSON response."""

    latitude: float
    longitude: float
    generationtime_ms: float | None = None
    utc_offset_seconds: int | None = None
    timezone: str | None = None
    elevation: float | None = None
    hourly_units: dict[str, str] | None = None
    hourly: HourlySeries | None = None
    current_units: dict[str, str] | None = None
    current: CurrentWeather | None = None


class NormalizedWeatherObservation(StrictModel):
    """Internal weather observation aligned with the persistence layer fields."""

    observed_at: datetime
    latitude: Decimal
    longitude: Decimal
    temperature_c: Decimal | None = None
    relative_humidity_pct: Decimal | None = None
    precipitation_mm: Decimal | None = None
    wind_speed_ms: Decimal | None = None
    wind_direction_deg: Decimal | None = None
    pressure_hpa: Decimal | None = None
    source: str = "open-meteo"
    raw_record_id: str

    def has_any_measurement(self) -> bool:
        """Return True when at least one weather variable is present."""
        return any(
            value is not None
            for value in (
                self.temperature_c,
                self.relative_humidity_pct,
                self.precipitation_mm,
                self.wind_speed_ms,
                self.wind_direction_deg,
                self.pressure_hpa,
            )
        )


class WeatherObservationBundle(StrictModel):
    """Normalized weather row plus the original API JSON fragment for archival."""

    observation: NormalizedWeatherObservation
    raw_payload: dict[str, Any]
    response_meta: dict[str, Any] = Field(default_factory=dict)
