"""Open-Meteo weather client package."""

from lahore_aqi_poller.clients.openmeteo.client import OpenMeteoClient
from lahore_aqi_poller.clients.openmeteo.exceptions import (
    OpenMeteoAPIError,
    OpenMeteoConfigError,
    OpenMeteoError,
    OpenMeteoRateLimitError,
    OpenMeteoTransientError,
)
from lahore_aqi_poller.clients.openmeteo.models import (
    GeoPoint,
    NormalizedWeatherObservation,
    WeatherObservationBundle,
)
from lahore_aqi_poller.clients.openmeteo.normalize import (
    normalize_current,
    normalize_hourly,
)

__all__ = [
    "GeoPoint",
    "NormalizedWeatherObservation",
    "OpenMeteoAPIError",
    "OpenMeteoClient",
    "OpenMeteoConfigError",
    "OpenMeteoError",
    "OpenMeteoRateLimitError",
    "OpenMeteoTransientError",
    "WeatherObservationBundle",
    "normalize_current",
    "normalize_hourly",
]
