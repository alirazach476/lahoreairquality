"""Documented input columns from the warehouse feature mart.

Source of truth for available fields: ``marts.mart_air_quality_features``
(``dbt/lahore_air_quality/models/marts/mart_air_quality_features.sql``).

Inspected grain: ``(station_id, observed_hour)``.
"""

from __future__ import annotations

from typing import Final

SOURCE_MART: Final[str] = "marts.mart_air_quality_features"

# Keys / time
KEY_COLUMNS: Final[tuple[str, ...]] = ("station_id", "observed_hour")

# Air-quality concentrations + AQI available on the mart (numeric series we lag/roll)
AQ_SERIES_COLUMNS: Final[tuple[str, ...]] = (
    "pm25",
    "pm10",
    "o3",
    "no2",
    "so2",
    "co",
    "station_aqi",
    "city_aqi",
)

# Weather fields present on the mart (same-hour join)
WEATHER_COLUMNS: Final[tuple[str, ...]] = (
    "temperature_c",
    "relative_humidity_pct",
    "wind_speed_ms",
    "wind_direction_deg",
    "pressure_hpa",
    "precipitation_mm",
)

# Present on the mart but not used as lag/rolling inputs (IDs, categories, lineage)
PASSTHROUGH_COLUMNS: Final[tuple[str, ...]] = (
    "location_name",
    "latitude",
    "longitude",
    "source_name",
    "station_aqi_category",
    "station_dominant_pollutant",
    "city_aqi_category",
    "city_dominant_pollutant",
    "observation_count",
    "last_ingested_at_utc",
)

# Precomputed on mart; we recompute causal rollings in Python instead of trusting this
# as a training feature (SQL window includes the current hour — fine for T, but we
# own the definition in the ML layer).
MART_PRECOMPUTED_ROLLING: Final[tuple[str, ...]] = ("pm25_rolling_24h_avg",)

REQUIRED_INPUT_COLUMNS: Final[tuple[str, ...]] = KEY_COLUMNS + AQ_SERIES_COLUMNS + WEATHER_COLUMNS

DEFAULT_LAGS: Final[tuple[int, ...]] = (1, 2, 3, 6, 12, 24)
DEFAULT_ROLLING_WINDOWS: Final[tuple[int, ...]] = (3, 6, 12, 24)
DEFAULT_TARGET_LEADS: Final[tuple[int, ...]] = (1, 3, 6, 12, 24)
