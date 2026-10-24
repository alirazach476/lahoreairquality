"""Health check schemas."""

from __future__ import annotations

from lahore_aqi_api.schemas.common import APIModel


class HealthResponse(APIModel):
    status: str = "ok"
    service: str = "lahore-aqi-api"
    version: str
    database: str
    database_message: str | None = None
