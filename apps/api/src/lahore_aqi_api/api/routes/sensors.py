"""GET /api/sensors"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from lahore_aqi_api.core.deps import RepoDep
from lahore_aqi_api.schemas.sensors import SensorsResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["sensors"])


@router.get(
    "/sensors",
    response_model=SensorsResponse,
    summary="Known monitoring stations / sensors",
)
def list_sensors(repo: RepoDep) -> SensorsResponse:
    result = repo.list_sensors()
    logger.info("sensors_listed count=%s", result.count)
    return result
