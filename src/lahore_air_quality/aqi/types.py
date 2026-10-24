"""Public types for the AQI calculation layer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Literal

PollutantCode = Literal["pm25", "pm10", "o3", "no2", "so2", "co"]


class AveragingPeriod(StrEnum):
    """EPA averaging period required for the published AQI of each pollutant."""

    HOUR_1 = "1-hour"
    HOUR_8 = "8-hour"
    HOUR_24 = "24-hour"


class AqiStatus(StrEnum):
    """Why a sub-index / overall AQI was or was not produced."""

    OK = "ok"
    MISSING_VALUE = "missing_value"
    INVALID_UNIT = "invalid_unit"
    UNSUPPORTED_POLLUTANT = "unsupported_pollutant"
    BELOW_SUPPORTED_RANGE = "below_supported_range"
    ABOVE_SUPPORTED_RANGE = "above_supported_range"
    INVALID_CONCENTRATION = "invalid_concentration"
    AVERAGING_PERIOD_MISMATCH = "averaging_period_mismatch"
    INSUFFICIENT_INPUT = "insufficient_input"


class AqiCategory(StrEnum):
    GOOD = "Good"
    MODERATE = "Moderate"
    UNHEALTHY_SENSITIVE = "Unhealthy for Sensitive Groups"
    UNHEALTHY = "Unhealthy"
    VERY_UNHEALTHY = "Very Unhealthy"
    HAZARDOUS = "Hazardous"


@dataclass(frozen=True, slots=True)
class PollutantReading:
    """One pollutant concentration offered to the AQI calculator."""

    pollutant: str
    concentration: Decimal | float | int | None
    unit: str
    averaging_period: AveragingPeriod | str | None = None


@dataclass(frozen=True, slots=True)
class SubIndexResult:
    """Result of calculating a single-pollutant AQI sub-index."""

    status: AqiStatus
    pollutant: str | None
    aqi: int | None
    category: AqiCategory | None
    concentration_truncated: Decimal | None
    unit: str | None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is AqiStatus.OK and self.aqi is not None


@dataclass(frozen=True, slots=True)
class AqiResult:
    """Overall AQI = maximum of available valid pollutant sub-indices."""

    status: AqiStatus
    aqi: int | None
    category: AqiCategory | None
    dominant_pollutant: str | None
    sub_indices: tuple[SubIndexResult, ...]
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is AqiStatus.OK and self.aqi is not None
