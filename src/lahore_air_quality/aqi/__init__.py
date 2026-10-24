"""US EPA Air Quality Index (AQI) calculation.

Authoritative methodology and project applicability: ``docs/aqi.md``.
Breakpoints are taken from EPA published tables — never invented ad hoc.
"""

from lahore_air_quality.aqi.calculate import (
    calculate_aqi,
    calculate_sub_index,
)
from lahore_air_quality.aqi.types import (
    AqiCategory,
    AqiResult,
    AqiStatus,
    AveragingPeriod,
    PollutantCode,
    PollutantReading,
    SubIndexResult,
)

__all__ = [
    "AveragingPeriod",
    "AqiCategory",
    "AqiResult",
    "AqiStatus",
    "PollutantCode",
    "PollutantReading",
    "SubIndexResult",
    "calculate_aqi",
    "calculate_sub_index",
]
