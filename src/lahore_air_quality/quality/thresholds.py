"""Documented thresholds for quality rules (see docs/data-quality.md)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Final

from lahore_air_quality.aqi.breakpoints import POLLUTANT_SPECS, normalize_pollutant_code

# Clock skew: small future skew is suspect; large skew is invalid.
FUTURE_SUSPECT_TOLERANCE: Final[timedelta] = timedelta(minutes=5)
FUTURE_INVALID_TOLERANCE: Final[timedelta] = timedelta(hours=1)

# Physical / defensive ceilings (invalid above these).
AQ_INVALID_CEILING: Final[dict[str, Decimal]] = {
    "pm25": Decimal("2000"),
    "pm10": Decimal("3000"),
    "o3": Decimal("1"),  # ppm
    "co": Decimal("100"),  # ppm
    "so2": Decimal("5000"),  # ppb
    "no2": Decimal("5000"),  # ppb
}

# Abnormal-but-plausible band → suspect (between EPA AQI-500 high and invalid ceiling).
AQ_SUSPECT_CEILING: Final[dict[str, Decimal]] = {
    "pm25": Decimal("325.4"),  # EPA AQI 500 high
    "pm10": Decimal("604"),
    "o3": Decimal("0.200"),
    "co": Decimal("50.4"),
    "so2": Decimal("1004"),
    "no2": Decimal("2049"),
}

# Expected units per canonical pollutant (aliases handled in rules).
EXPECTED_UNITS: Final[dict[str, frozenset[str]]] = {
    "pm25": frozenset({"µg/m³", "ug/m³", "ug/m3", "µg/m3"}),
    "pm10": frozenset({"µg/m³", "ug/m³", "ug/m3", "µg/m3"}),
    "o3": frozenset({"ppm"}),
    "co": frozenset({"ppm"}),
    "so2": frozenset({"ppb"}),
    "no2": frozenset({"ppb"}),
}

# Weather physical ranges (outside → invalid).
WEATHER_RANGES: Final[dict[str, tuple[Decimal, Decimal]]] = {
    "temperature_c": (Decimal("-90"), Decimal("60")),
    "relative_humidity_pct": (Decimal("0"), Decimal("100")),
    "precipitation_mm": (Decimal("0"), Decimal("500")),
    "wind_speed_ms": (Decimal("0"), Decimal("150")),
    "wind_direction_deg": (Decimal("0"), Decimal("360")),
    "pressure_hpa": (Decimal("800"), Decimal("1100")),
}

# Report / observability defaults.
STALE_AFTER: Final[timedelta] = timedelta(hours=12)
SENSOR_INACTIVE_AFTER: Final[timedelta] = timedelta(hours=6)
EXPECTED_AQ_INTERVAL: Final[timedelta] = timedelta(hours=1)
GAP_FACTOR: Final[float] = 3.0  # gap > factor * expected → missing interval
# Pipeline delay: ingested_at − observed_at (late arrival / backlog).
DELAYED_INGEST_AFTER: Final[timedelta] = timedelta(hours=6)


def canonical_pollutant(raw: str | None) -> str | None:
    if raw is None:
        return None
    return normalize_pollutant_code(raw)


def known_pollutant_codes() -> frozenset[str]:
    return frozenset(POLLUTANT_SPECS.keys())
