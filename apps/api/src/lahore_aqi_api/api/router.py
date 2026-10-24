"""Aggregate API routers."""

from __future__ import annotations

from fastapi import APIRouter

from lahore_aqi_api.api.routes import (
    air_quality,
    data_quality,
    forecast,
    health,
    resilience,
    sensors,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(resilience.router)
api_router.include_router(air_quality.router)
api_router.include_router(forecast.router)
api_router.include_router(sensors.router)
api_router.include_router(data_quality.router)
