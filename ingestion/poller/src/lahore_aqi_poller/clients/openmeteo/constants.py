"""Open-Meteo API constants.

Lahore coordinates are **not** defined here — they come from configurable
settings (``LAHORE_LATITUDE`` / ``LAHORE_LONGITUDE``).
"""

from __future__ import annotations

SOURCE_NAME = "open-meteo"

# Documented Open-Meteo endpoints (relative to the respective base URLs).
FORECAST_PATH = "/v1/forecast"
ARCHIVE_PATH = "/v1/archive"

# Hourly / current variables required for ML features.
# Docs: https://open-meteo.com/en/docs and Historical Weather API docs.
HOURLY_VARIABLES: tuple[str, ...] = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "wind_direction_10m",
    "surface_pressure",
)

# Request wind in m/s to match ``WeatherObservation.wind_speed_ms``.
WIND_SPEED_UNIT = "ms"
TIMEZONE = "UTC"

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_FORECAST_DAYS = 7
DEFAULT_PAST_DAYS = 1

TRANSIENT_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
