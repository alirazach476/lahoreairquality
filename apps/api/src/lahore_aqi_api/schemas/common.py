"""Shared response fragments."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        ser_json_timedelta="iso8601",
    )


class DataFreshness(APIModel):
    observed_at: datetime
    age_seconds: float = Field(ge=0)
    is_fresh: bool
    freshness_threshold_seconds: int = Field(ge=60)


class ErrorResponse(APIModel):
    error: dict[str, object]
