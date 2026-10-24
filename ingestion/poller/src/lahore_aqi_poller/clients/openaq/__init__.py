"""OpenAQ API v3 client package."""

from lahore_aqi_poller.clients.openaq.client import OpenAQClient
from lahore_aqi_poller.clients.openaq.exceptions import (
    OpenAQAPIError,
    OpenAQAuthError,
    OpenAQConfigError,
    OpenAQError,
    OpenAQRateLimitError,
    OpenAQTransientError,
)
from lahore_aqi_poller.clients.openaq.models import (
    NormalizedAirQualityObservation,
    ObservationBundle,
    OpenAQLocation,
)
from lahore_aqi_poller.clients.openaq.normalize import (
    normalize_latest_measurement,
    normalize_latest_results,
    normalize_sensor_measurement,
    normalize_sensor_results,
)

__all__ = [
    "NormalizedAirQualityObservation",
    "ObservationBundle",
    "OpenAQAPIError",
    "OpenAQAuthError",
    "OpenAQClient",
    "OpenAQConfigError",
    "OpenAQError",
    "OpenAQLocation",
    "OpenAQRateLimitError",
    "OpenAQTransientError",
    "normalize_latest_measurement",
    "normalize_latest_results",
    "normalize_sensor_measurement",
    "normalize_sensor_results",
]
