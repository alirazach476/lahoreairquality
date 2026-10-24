"""Sensor / station listing schemas."""

from __future__ import annotations

from datetime import datetime

from lahore_aqi_api.schemas.common import APIModel


class SensorInfo(APIModel):
    station_id: str
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source_name: str | None = None
    last_observed_at: datetime | None = None
    observation_count: int | None = None


class SensorsResponse(APIModel):
    sensors: list[SensorInfo]
    count: int
