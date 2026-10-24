"""OpenAQ v3 constants and Lahore discovery geography.

Sensor and location IDs are never hard-coded here — they are discovered at
runtime from the OpenAQ API. Only geographic search parameters for Lahore are
defined so the client can find available monitors.
"""

from __future__ import annotations

SOURCE_NAME = "openaq"
API_VERSION_PREFIX = "/v3"

# Geographic discovery for Lahore, Pakistan (WGS84).
# OpenAQ ``radius`` max is 25_000 meters per documented API.
LAHORE_CENTER_LATITUDE = 31.5204
LAHORE_CENTER_LONGITUDE = 74.3587
LAHORE_DEFAULT_RADIUS_M = 25_000
LAHORE_COUNTRY_ISO = "PK"

# Default HTTP behaviour
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_PAGE_LIMIT = 100
# Stay under the documented free tier (60/min) with a small safety margin.
MIN_REQUEST_INTERVAL_SECONDS = 1.05

TRANSIENT_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
