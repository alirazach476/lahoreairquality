"""GET /api/forecast"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from lahore_aqi_api.core.deps import RepoDep
from lahore_aqi_api.core.errors import error_body
from lahore_aqi_api.schemas.forecast import ForecastResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["forecast"])


@router.get(
    "/forecast",
    response_model=ForecastResponse,
    summary="Latest model forecasts",
    responses={404: {"description": "No forecasts available"}},
)
def get_forecast(
    repo: RepoDep,
    station_id: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=24, ge=1, le=168),
) -> ForecastResponse:
    result = repo.get_forecasts(station_id=station_id, limit=limit)
    if result.count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_body(
                code="not_found",
                message="No forecasts available",
                details={"station_id": station_id},
            ),
        )
    logger.info("forecast_served count=%s station_id=%s", result.count, station_id)
    return result
