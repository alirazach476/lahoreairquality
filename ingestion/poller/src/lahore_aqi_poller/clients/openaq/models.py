"""Pydantic models for OpenAQ v3 payloads and normalized observations."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    """Base model that ignores unknown OpenAQ fields for forward compatibility."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Coordinates(StrictModel):
    latitude: float | None = None
    longitude: float | None = None


class DatetimeObject(StrictModel):
    utc: str
    local: str | None = None


class ParameterBase(StrictModel):
    id: int
    name: str
    units: str
    display_name: str | None = Field(default=None, alias="displayName")


class SensorBase(StrictModel):
    id: int
    name: str | None = None
    parameter: ParameterBase


class CountryBase(StrictModel):
    id: int | None = None
    code: str
    name: str


class ProviderBase(StrictModel):
    id: int
    name: str


class OpenAQLocation(StrictModel):
    """A monitoring location returned by ``GET /v3/locations``."""

    id: int
    name: str | None = None
    locality: str | None = None
    timezone: str | None = None
    country: CountryBase | None = None
    provider: ProviderBase | None = None
    is_mobile: bool | None = Field(default=None, alias="isMobile")
    is_monitor: bool | None = Field(default=None, alias="isMonitor")
    sensors: list[SensorBase] = Field(default_factory=list)
    coordinates: Coordinates | None = None
    datetime_first: DatetimeObject | None = Field(default=None, alias="datetimeFirst")
    datetime_last: DatetimeObject | None = Field(default=None, alias="datetimeLast")

    @property
    def sensor_by_id(self) -> dict[int, SensorBase]:
        return {sensor.id: sensor for sensor in self.sensors}


class LatestMeasurement(StrictModel):
    """A row from ``GET /v3/locations/{id}/latest``."""

    datetime: DatetimeObject
    value: float | int
    coordinates: Coordinates | None = None
    sensors_id: int = Field(alias="sensorsId")
    locations_id: int = Field(alias="locationsId")


class MeasurementPeriod(StrictModel):
    label: str | None = None
    interval: str | None = None
    datetime_from: DatetimeObject | None = Field(default=None, alias="datetimeFrom")
    datetime_to: DatetimeObject | None = Field(default=None, alias="datetimeTo")


class SensorMeasurement(StrictModel):
    """A row from ``GET /v3/sensors/{id}/measurements``."""

    value: float | int | None = None
    parameter: ParameterBase | None = None
    period: MeasurementPeriod | None = None
    coordinates: Coordinates | None = None


class NormalizedAirQualityObservation(StrictModel):
    """Internal normalized observation aligned with the persistence layer fields."""

    observation_id: str | None = None
    station_id: str
    location_name: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    pollutant: str
    value: Decimal
    unit: str
    observed_at: datetime
    source: str = "openaq"
    raw_record_id: str

    @field_validator("pollutant")
    @classmethod
    def normalize_pollutant_name(cls, value: str) -> str:
        cleaned = value.strip().lower().replace(" ", "")
        if not cleaned:
            msg = "pollutant must not be blank"
            raise ValueError(msg)
        # Common OpenAQ spellings → compact keys used in AQI logic later.
        aliases = {
            "pm2.5": "pm25",
            "pm25": "pm25",
            "pm10": "pm10",
            "o3": "o3",
            "no2": "no2",
            "so2": "so2",
            "co": "co",
        }
        return aliases.get(cleaned, cleaned)


class ObservationBundle(StrictModel):
    """Normalized observation plus the original API JSON for archival."""

    observation: NormalizedAirQualityObservation
    raw_payload: dict[str, Any]
    location: OpenAQLocation | None = None
