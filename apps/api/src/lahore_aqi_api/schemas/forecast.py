"""Forecast response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from lahore_aqi_api.schemas.common import APIModel


class ForecastPoint(APIModel):
    forecast_timestamp: datetime
    predicted_aqi: float
    model_name: str
    model_version: str
    forecast_horizon: int = Field(ge=1, description="Horizon in hours")
    station_id: str | None = None
    origin_timestamp: datetime | None = None


class ForecastResponse(APIModel):
    generated_at: datetime
    forecasts: list[ForecastPoint]
    count: int
