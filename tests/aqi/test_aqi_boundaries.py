"""Breakpoint-boundary tests required by the AQI calculation layer.

Covers, for supported pollutants (focus PM2.5 — the pollutant actually present
in Lahore OpenAQ/AirNow fixtures):

- below the first breakpoint
- exactly at a lower breakpoint
- between breakpoints
- exactly at an upper breakpoint
- above the supported AQI≤500 range
- missing value
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from lahore_air_quality.aqi import calculate_aqi, calculate_sub_index
from lahore_air_quality.aqi.types import (
    AqiCategory,
    AqiStatus,
    AveragingPeriod,
    PollutantReading,
)

PM25_UNIT = "µg/m³"


# ---------------------------------------------------------------------------
# Missing / invalid inputs
# ---------------------------------------------------------------------------


def test_missing_value_returns_no_aqi() -> None:
    result = calculate_sub_index("pm25", None, PM25_UNIT)
    assert result.status is AqiStatus.MISSING_VALUE
    assert result.aqi is None
    assert result.category is None
    assert not result.ok


def test_wrong_unit_returns_no_aqi() -> None:
    result = calculate_sub_index("pm25", 12.0, "ppm")
    assert result.status is AqiStatus.INVALID_UNIT
    assert result.aqi is None


def test_unsupported_pollutant_returns_no_aqi() -> None:
    result = calculate_sub_index("benzene", 1.0, "ppb")
    assert result.status is AqiStatus.UNSUPPORTED_POLLUTANT
    assert result.aqi is None


# ---------------------------------------------------------------------------
# Below / above supported range
# ---------------------------------------------------------------------------


def test_below_first_breakpoint_returns_no_aqi() -> None:
    # First PM2.5 band starts at 0.0 µg/m³; negative is below supported range.
    result = calculate_sub_index("pm25", Decimal("-0.1"), PM25_UNIT)
    assert result.status is AqiStatus.BELOW_SUPPORTED_RANGE
    assert result.aqi is None
    assert result.concentration_truncated == Decimal("-0.1")


def test_above_supported_range_returns_no_aqi() -> None:
    # Last AQI≤500 band for PM2.5 ends at 325.4 µg/m³.
    result = calculate_sub_index("pm25", Decimal("325.5"), PM25_UNIT)
    assert result.status is AqiStatus.ABOVE_SUPPORTED_RANGE
    assert result.aqi is None
    assert result.concentration_truncated == Decimal("325.5")


def test_far_above_supported_range_returns_no_aqi() -> None:
    result = calculate_sub_index("pm25", 9999, PM25_UNIT)
    assert result.status is AqiStatus.ABOVE_SUPPORTED_RANGE
    assert result.aqi is None


# ---------------------------------------------------------------------------
# Exact breakpoints and interiors (PM2.5, 2024 EPA table)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("concentration", "expected_aqi", "expected_category"),
    [
        # Exactly at first band low / high
        (Decimal("0.0"), 0, AqiCategory.GOOD),
        (Decimal("9.0"), 50, AqiCategory.GOOD),
        # Exactly at next band low (Moderate starts at 9.1)
        (Decimal("9.1"), 51, AqiCategory.MODERATE),
        # Between Moderate breakpoints
        (Decimal("20.0"), 71, AqiCategory.MODERATE),
        # Exactly at Moderate high
        (Decimal("35.4"), 100, AqiCategory.MODERATE),
        # Exactly at USG low / high
        (Decimal("35.5"), 101, AqiCategory.UNHEALTHY_SENSITIVE),
        (Decimal("55.4"), 150, AqiCategory.UNHEALTHY_SENSITIVE),
        # Between Unhealthy (Lahore fixture-style value)
        (Decimal("87.5"), 173, AqiCategory.UNHEALTHY),
        # Exactly at Unhealthy high
        (Decimal("125.4"), 200, AqiCategory.UNHEALTHY),
        # Exactly at Very Unhealthy high
        (Decimal("225.4"), 300, AqiCategory.VERY_UNHEALTHY),
        # Exactly at Hazardous / AQI 500 ceiling
        (Decimal("225.5"), 301, AqiCategory.HAZARDOUS),
        (Decimal("325.4"), 500, AqiCategory.HAZARDOUS),
    ],
)
def test_pm25_breakpoint_boundaries(
    concentration: Decimal,
    expected_aqi: int,
    expected_category: AqiCategory,
) -> None:
    result = calculate_sub_index("pm25", concentration, PM25_UNIT)
    assert result.status is AqiStatus.OK
    assert result.aqi == expected_aqi
    assert result.category is expected_category


def test_truncation_before_lookup() -> None:
    # 9.09 truncates to 9.0 (1 decimal) → still Good / AQI 50 band high path
    result = calculate_sub_index("pm25", Decimal("9.09"), PM25_UNIT)
    assert result.ok
    assert result.concentration_truncated == Decimal("9.0")
    assert result.aqi == 50


def test_pm10_exact_and_above() -> None:
    at_low = calculate_sub_index("pm10", 0, "µg/m³")
    assert at_low.aqi == 0
    at_high = calculate_sub_index("pm10", 54, "ug/m3")
    assert at_high.aqi == 50
    above = calculate_sub_index("pm10", 605, "µg/m³")
    assert above.status is AqiStatus.ABOVE_SUPPORTED_RANGE
    assert above.aqi is None


# ---------------------------------------------------------------------------
# Overall AQI aggregation
# ---------------------------------------------------------------------------


def test_overall_aqi_uses_max_subindex() -> None:
    result = calculate_aqi(
        [
            PollutantReading("pm25", Decimal("9.0"), PM25_UNIT, AveragingPeriod.HOUR_24),
            PollutantReading("pm10", Decimal("155"), "µg/m³", AveragingPeriod.HOUR_24),
        ]
    )
    assert result.ok
    assert result.aqi == 101  # pm10 at USG low
    assert result.dominant_pollutant == "pm10"


def test_overall_aqi_skips_missing_pollutants() -> None:
    result = calculate_aqi(
        [
            PollutantReading("pm25", None, PM25_UNIT),
            PollutantReading("pm10", Decimal("54"), "µg/m³"),
        ]
    )
    assert result.ok
    assert result.aqi == 50
    assert result.dominant_pollutant == "pm10"


def test_overall_aqi_insufficient_when_all_invalid() -> None:
    result = calculate_aqi(
        [
            PollutantReading("pm25", None, PM25_UNIT),
            PollutantReading("pm25", Decimal("400"), PM25_UNIT),
        ]
    )
    assert result.status is AqiStatus.INSUFFICIENT_INPUT
    assert result.aqi is None
    assert not result.ok


def test_require_averaging_period_mismatch() -> None:
    result = calculate_sub_index(
        "pm25",
        Decimal("12.0"),
        PM25_UNIT,
        averaging_period=AveragingPeriod.HOUR_1,
        require_averaging_period=True,
    )
    assert result.status is AqiStatus.AVERAGING_PERIOD_MISMATCH
    assert result.aqi is None


def test_require_averaging_period_ok() -> None:
    result = calculate_sub_index(
        "pm25",
        Decimal("12.0"),
        PM25_UNIT,
        averaging_period=AveragingPeriod.HOUR_24,
        require_averaging_period=True,
    )
    assert result.ok
