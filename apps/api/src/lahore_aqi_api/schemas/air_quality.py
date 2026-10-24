"""Air-quality current / history schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from lahore_aqi_api.schemas.common import APIModel, DataFreshness


class PollutantReadings(APIModel):
    pm25: float | None = None
    pm10: float | None = None
    o3: float | None = None
    no2: float | None = None
    so2: float | None = None
    co: float | None = None


class WeatherReadings(APIModel):
    """Same-hour weather context from the feature mart (optional)."""

    temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    wind_speed_ms: float | None = None
    wind_direction_deg: float | None = None


class CurrentAirQualityResponse(APIModel):
    timestamp: datetime
    aqi: float = Field(ge=0, le=500)
    aqi_category: str | None = None
    dominant_pollutant: str | None = None
    pollutants: PollutantReadings
    weather: WeatherReadings = Field(default_factory=WeatherReadings)
    station_id: str | None = None
    scope: str = Field(
        description="city = Lahore aggregate; station = single sensor",
    )
    freshness: DataFreshness


class HistoryPoint(APIModel):
    timestamp: datetime
    aqi: float | None = None
    dominant_pollutant: str | None = None
    pollutants: PollutantReadings
    station_id: str | None = None


class AirQualityHistoryResponse(APIModel):
    start: datetime
    end: datetime
    station_id: str | None = None
    points: list[HistoryPoint]
    count: int
