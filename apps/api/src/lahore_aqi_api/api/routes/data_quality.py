"""GET /api/data-quality"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from lahore_aqi_api.core.deps import RepoDep
from lahore_aqi_api.schemas.quality import DataQualityResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["data-quality"])


@router.get(
    "/data-quality",
    response_model=DataQualityResponse,
    summary="Data-quality monitoring summary",
)
def get_data_quality(repo: RepoDep) -> DataQualityResponse:
    result = repo.get_data_quality()
    logger.info(
        "data_quality_served aq_rows=%s db_healthy=%s",
        result.air_quality_rows_evaluated,
        result.database_healthy,
    )
    return result
