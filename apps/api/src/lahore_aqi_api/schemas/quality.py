"""Data-quality summary schemas."""

from __future__ import annotations

from datetime import datetime

from lahore_aqi_api.schemas.common import APIModel


class QualityClassCounts(APIModel):
    valid: int = 0
    suspect: int = 0
    invalid: int = 0


class DataQualityResponse(APIModel):
    evaluated_at: datetime
    database_healthy: bool
    air_quality_rows_evaluated: int
    weather_rows_evaluated: int
    class_counts: QualityClassCounts
    inactive_stations: list[str] = []
    notes: list[str] = []
    rules_doc: str = "docs/data-quality.md"
