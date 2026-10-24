"""Additional deterministic AQI unit tests (truncation, categories, multi-pollutant)."""

from __future__ import annotations

from decimal import Decimal

from lahore_air_quality.aqi import calculate_sub_index
from lahore_air_quality.aqi.categories import category_for_aqi
from lahore_air_quality.aqi.truncate import truncate_concentration
from lahore_air_quality.aqi.types import AqiCategory, AqiStatus


def test_truncate_pm25_and_pm10() -> None:
    assert truncate_concentration("pm25", Decimal("12.99")) == Decimal("12.9")
    assert truncate_concentration("pm10", Decimal("54.9")) == Decimal("54")


def test_category_edges() -> None:
    assert category_for_aqi(0) is AqiCategory.GOOD
    assert category_for_aqi(50) is AqiCategory.GOOD
    assert category_for_aqi(51) is AqiCategory.MODERATE
    assert category_for_aqi(100) is AqiCategory.MODERATE
    assert category_for_aqi(101) is AqiCategory.UNHEALTHY_SENSITIVE
    assert category_for_aqi(301) is AqiCategory.HAZARDOUS
    assert category_for_aqi(500) is AqiCategory.HAZARDOUS


def test_ug_m3_unit_aliases() -> None:
    a = calculate_sub_index("pm25", 9.0, "µg/m³")
    b = calculate_sub_index("pm25", 9.0, "ug/m3")
    assert a.aqi == b.aqi == 50


def test_o3_requires_ppm() -> None:
    bad = calculate_sub_index("o3", 0.05, "µg/m³")
    assert bad.status is AqiStatus.INVALID_UNIT
    good = calculate_sub_index("o3", Decimal("0.054"), "ppm")
    assert good.aqi == 50
