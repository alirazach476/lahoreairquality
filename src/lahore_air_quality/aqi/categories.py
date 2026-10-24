"""Map numeric AQI to EPA category labels."""

from __future__ import annotations

from lahore_air_quality.aqi.types import AqiCategory


def category_for_aqi(aqi: int) -> AqiCategory:
    if aqi <= 50:
        return AqiCategory.GOOD
    if aqi <= 100:
        return AqiCategory.MODERATE
    if aqi <= 150:
        return AqiCategory.UNHEALTHY_SENSITIVE
    if aqi <= 200:
        return AqiCategory.UNHEALTHY
    if aqi <= 300:
        return AqiCategory.VERY_UNHEALTHY
    return AqiCategory.HAZARDOUS
