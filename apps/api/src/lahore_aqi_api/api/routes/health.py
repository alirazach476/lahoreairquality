"""GET /health"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status

from lahore_air_quality.db.health import DatabaseHealth, check_database_health
from lahore_aqi_api.core.config import get_api_settings
from lahore_aqi_api.schemas.health import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service and database health",
)
def health(request: Request, response: Response) -> HealthResponse:
    settings = get_api_settings()
    checker = getattr(request.app.state, "health_checker", None)
    db: DatabaseHealth = checker() if callable(checker) else check_database_health()
    if not db.healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning("health_degraded database=unavailable")
    return HealthResponse(
        status="ok" if db.healthy else "degraded",
        version=settings.api_version,
        database="up" if db.healthy else "down",
        database_message=db.message,
    )
