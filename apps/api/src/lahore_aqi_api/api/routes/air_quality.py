"""Air-quality current and history endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from lahore_aqi_api.core.deps import ApiConfigDep, RepoDep
from lahore_aqi_api.core.errors import error_body
from lahore_aqi_api.schemas.air_quality import (
    AirQualityHistoryResponse,
    CurrentAirQualityResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/air-quality", tags=["air-quality"])


@router.get(
    "/current",
    response_model=CurrentAirQualityResponse,
    summary="Latest AQI snapshot",
    responses={404: {"description": "No air-quality observations available"}},
)
def get_current_air_quality(
    repo: RepoDep,
    station_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=128,
        description="Optional station filter; omit for city-level AQI",
    ),
) -> CurrentAirQualityResponse:
    current = repo.get_current(station_id=station_id)
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_body(
                code="not_found",
                message="No current air-quality observation available",
                details={"station_id": station_id},
            ),
        )
    logger.info(
        "current_aqi scope=%s station_id=%s aqi=%s fresh=%s",
        current.scope,
        current.station_id,
        current.aqi,
        current.freshness.is_fresh,
    )
    return current


@router.get(
    "/history",
    response_model=AirQualityHistoryResponse,
    summary="Recent AQI / pollutant history",
)
def get_air_quality_history(
    repo: RepoDep,
    settings: ApiConfigDep,
    hours: int = Query(
        default=None,
        ge=1,
        description="Lookback window in hours",
    ),
    station_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=128,
    ),
) -> AirQualityHistoryResponse:
    window = hours if hours is not None else settings.history_default_hours
    if window > settings.history_max_hours:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_body(
                code="validation_error",
                message=f"hours must be <= {settings.history_max_hours}",
                details={"hours": window, "max": settings.history_max_hours},
            ),
        )
    history = repo.get_history(hours=window, station_id=station_id)
    logger.info(
        "history_aqi hours=%s station_id=%s count=%s",
        window,
        station_id,
        history.count,
    )
    return history
