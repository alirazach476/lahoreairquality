"""OpenAQ API v3 client.

Uses the currently documented OpenAQ v3 endpoints and ``X-API-Key`` auth.
See https://docs.openaq.org/
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import httpx

from lahore_aqi_poller.clients.openaq.constants import (
    API_VERSION_PREFIX,
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    LAHORE_CENTER_LATITUDE,
    LAHORE_CENTER_LONGITUDE,
    LAHORE_COUNTRY_ISO,
    LAHORE_DEFAULT_RADIUS_M,
    MIN_REQUEST_INTERVAL_SECONDS,
    TRANSIENT_STATUS_CODES,
)
from lahore_aqi_poller.clients.openaq.exceptions import (
    OpenAQAPIError,
    OpenAQAuthError,
    OpenAQConfigError,
    OpenAQRateLimitError,
    OpenAQTransientError,
)
from lahore_aqi_poller.clients.openaq.models import (
    ObservationBundle,
    OpenAQLocation,
)
from lahore_aqi_poller.clients.openaq.normalize import (
    normalize_latest_results,
    normalize_sensor_results,
)

logger = logging.getLogger(__name__)


def _redact_headers(headers: httpx.Headers | dict[str, str]) -> dict[str, str]:
    """Return headers safe for logging (API key removed)."""
    redacted: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in {"x-api-key", "authorization"}:
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


class OpenAQClient:
    """Reusable HTTP client for OpenAQ API v3.

    Credentials are supplied via constructor or :meth:`from_settings` — never
    hard-coded. This client does **not** run a continuous poller.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openaq.org",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        min_request_interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise OpenAQConfigError(
                "OPENAQ_API_KEY is required. Set it in the environment "
                "(see .env.example) — never hard-code the key."
            )

        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._min_request_interval_seconds = min_request_interval_seconds
        self._last_request_monotonic = 0.0

        timeout = httpx.Timeout(
            timeout_seconds,
            connect=connect_timeout_seconds,
        )
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "X-API-Key": self._api_key,
                "User-Agent": "lahore-air-quality-openaq-client/0.1",
            },
            transport=transport,
            follow_redirects=True,
        )

    @classmethod
    def from_settings(cls, settings: Any | None = None) -> OpenAQClient:
        """Build a client from :class:`lahore_air_quality.config.Settings`."""
        if settings is None:
            from lahore_air_quality.config import get_settings

            settings = get_settings()
        return cls(
            api_key=settings.openaq_api_key.get_secret_value(),
            base_url=settings.openaq_base_url,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> OpenAQClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_lahore_locations(
        self,
        *,
        radius_m: int = LAHORE_DEFAULT_RADIUS_M,
        limit: int = DEFAULT_PAGE_LIMIT,
        name_contains: str | None = "lahore",
    ) -> list[OpenAQLocation]:
        """Discover OpenAQ locations near Lahore via the live API.

        Uses geographic search (coordinates + radius) and Pakistan ISO code.
        Location/sensor IDs are taken from the API response — never hard-coded.

        Args:
            radius_m: Search radius in meters (OpenAQ max 25_000).
            limit: Page size for location listing.
            name_contains: Optional case-insensitive filter on ``name`` /
                ``locality``. Pass ``None`` to keep all geo matches.
        """
        if radius_m <= 0 or radius_m > 25_000:
            raise ValueError("radius_m must be between 1 and 25000 (OpenAQ limit)")

        coordinates = f"{LAHORE_CENTER_LATITUDE},{LAHORE_CENTER_LONGITUDE}"
        logger.info(
            "Discovering OpenAQ locations near Lahore coordinates=%s radius_m=%s iso=%s",
            coordinates,
            radius_m,
            LAHORE_COUNTRY_ISO,
        )

        raw_locations = self.list_locations(
            coordinates=coordinates,
            radius=radius_m,
            iso=LAHORE_COUNTRY_ISO,
            limit=limit,
        )
        locations = self._parse_locations(raw_locations)

        if name_contains:
            needle = name_contains.casefold()
            filtered = [
                loc
                for loc in locations
                if (loc.name and needle in loc.name.casefold())
                or (loc.locality and needle in loc.locality.casefold())
            ]
            # If the name filter removes everything but geo matches exist, keep
            # geo matches — names/localities are not always populated as "Lahore".
            if filtered:
                locations = filtered
            else:
                logger.warning(
                    "Name filter %r matched 0 of %s Lahore-area locations; "
                    "keeping geographic matches",
                    name_contains,
                    len(locations),
                )

        logger.info(
            "Discovered %s OpenAQ location(s) for Lahore (sensors total=%s)",
            len(locations),
            sum(len(loc.sensors) for loc in locations),
        )
        return locations

    def list_locations(
        self,
        *,
        coordinates: str | None = None,
        radius: int | None = None,
        iso: str | None = None,
        bbox: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch raw location dicts from ``GET /v3/locations`` (paginated)."""
        params: dict[str, Any] = {"limit": limit}
        if coordinates is not None:
            params["coordinates"] = coordinates
        if radius is not None:
            params["radius"] = radius
        if iso is not None:
            params["iso"] = iso
        if bbox is not None:
            params["bbox"] = bbox

        return self._paginate("/locations", params=params, max_pages=max_pages)

    # ------------------------------------------------------------------
    # Recent / historical measurements
    # ------------------------------------------------------------------

    def fetch_location_latest_raw(
        self,
        location_id: int,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> list[dict[str, Any]]:
        """Fetch raw latest measurement rows for a location."""
        path = f"/locations/{location_id}/latest"
        payload = self._request_json("GET", path, params={"limit": limit, "page": 1})
        results = payload.get("results")
        if results is None:
            logger.info("Empty/missing results for location latest location_id=%s", location_id)
            return []
        if not isinstance(results, list):
            raise OpenAQAPIError(
                f"Unexpected results type for {path}: {type(results).__name__}",
                path=path,
            )
        if not results:
            logger.info("No latest measurements for location_id=%s", location_id)
        return [row for row in results if isinstance(row, dict)]

    def fetch_recent_measurements(
        self,
        *,
        locations: list[OpenAQLocation] | None = None,
        radius_m: int = LAHORE_DEFAULT_RADIUS_M,
    ) -> list[ObservationBundle]:
        """Discover Lahore locations (if needed) and fetch/normalize latest values."""
        resolved = (
            locations
            if locations is not None
            else self.discover_lahore_locations(radius_m=radius_m)
        )
        if not resolved:
            logger.warning("No Lahore locations available; returning no measurements")
            return []

        bundles: list[ObservationBundle] = []
        for location in resolved:
            raw_rows = self.fetch_location_latest_raw(location.id)
            bundles.extend(normalize_latest_results(raw_rows, location=location))
        return bundles

    def fetch_sensor_measurements_raw(
        self,
        sensor_id: int,
        *,
        datetime_from: datetime | None = None,
        datetime_to: datetime | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch raw historical rows from ``GET /v3/sensors/{id}/measurements``."""
        params: dict[str, Any] = {"limit": limit}
        if datetime_from is not None:
            params["datetime_from"] = _format_openaq_datetime(datetime_from)
        if datetime_to is not None:
            params["datetime_to"] = _format_openaq_datetime(datetime_to)

        path = f"/sensors/{sensor_id}/measurements"
        return self._paginate(path, params=params, max_pages=max_pages)

    def fetch_historical_measurements(
        self,
        sensor_id: int,
        *,
        datetime_from: datetime | None = None,
        datetime_to: datetime | None = None,
        location: OpenAQLocation | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        max_pages: int | None = None,
    ) -> list[ObservationBundle]:
        """Fetch and normalize historical measurements for a discovered sensor."""
        raw_rows = self.fetch_sensor_measurements_raw(
            sensor_id,
            datetime_from=datetime_from,
            datetime_to=datetime_to,
            limit=limit,
            max_pages=max_pages,
        )
        fallback_name = None
        fallback_unit = None
        if location is not None:
            sensor = location.sensor_by_id.get(sensor_id)
            if sensor is not None:
                fallback_name = sensor.parameter.name
                fallback_unit = sensor.parameter.units

        return normalize_sensor_results(
            raw_rows,
            sensor_id=sensor_id,
            location=location,
            fallback_parameter_name=fallback_name,
            fallback_unit=fallback_unit,
        )

    # ------------------------------------------------------------------
    # Normalization helpers (explicit public API)
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_measurements(
        results: list[dict[str, Any]],
        *,
        location: OpenAQLocation,
        mode: str = "latest",
        sensor_id: int | None = None,
    ) -> list[ObservationBundle]:
        """Normalize raw OpenAQ result rows into internal observation bundles."""
        if mode == "latest":
            return normalize_latest_results(results, location=location)
        if mode == "historical":
            if sensor_id is None:
                raise ValueError("sensor_id is required when mode='historical'")
            return normalize_sensor_results(results, sensor_id=sensor_id, location=location)
        raise ValueError("mode must be 'latest' or 'historical'")

    # ------------------------------------------------------------------
    # HTTP internals
    # ------------------------------------------------------------------

    def _parse_locations(self, raw_locations: list[dict[str, Any]]) -> list[OpenAQLocation]:
        locations: list[OpenAQLocation] = []
        for raw in raw_locations:
            try:
                locations.append(OpenAQLocation.model_validate(raw))
            except Exception:
                logger.exception(
                    "Skipping malformed OpenAQ location payload id=%s",
                    raw.get("id") if isinstance(raw, dict) else None,
                )
        return locations

    def _paginate(
        self,
        path: str,
        *,
        params: dict[str, Any],
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        page = 1
        collected: list[dict[str, Any]] = []
        limit = int(params.get("limit", DEFAULT_PAGE_LIMIT))

        while True:
            if max_pages is not None and page > max_pages:
                break

            page_params = {**params, "page": page}
            payload = self._request_json("GET", path, params=page_params)
            results = payload.get("results")
            if results is None:
                logger.info("Empty/missing results path=%s page=%s", path, page)
                break
            if not isinstance(results, list):
                raise OpenAQAPIError(
                    f"Unexpected results type for {path}: {type(results).__name__}",
                    path=path,
                )
            if not results:
                logger.info("No results path=%s page=%s", path, page)
                break

            page_rows = [row for row in results if isinstance(row, dict)]
            skipped = len(results) - len(page_rows)
            if skipped:
                logger.warning(
                    "Skipped %s non-object result row(s) path=%s page=%s",
                    skipped,
                    path,
                    page,
                )
            collected.extend(page_rows)

            meta = payload.get("meta") or {}
            found = meta.get("found")
            if _pages_exhausted(found=found, page=page, limit=limit, page_size=len(results)):
                break
            page += 1

        return collected

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_monotonic
        wait_for = self._min_request_interval_seconds - elapsed
        if wait_for > 0:
            time.sleep(wait_for)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        versioned_path = (
            path if path.startswith(API_VERSION_PREFIX) else f"{API_VERSION_PREFIX}{path}"
        )
        attempt = 0
        last_error: Exception | None = None

        while attempt <= self._max_retries:
            attempt += 1
            self._throttle()
            started = time.monotonic()
            try:
                response = self._client.request(method, versioned_path, params=params)
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "OpenAQ timeout method=%s path=%s attempt=%s/%s error=%s",
                    method,
                    versioned_path,
                    attempt,
                    self._max_retries + 1,
                    type(exc).__name__,
                )
                if attempt > self._max_retries:
                    raise OpenAQTransientError(
                        f"OpenAQ request timed out after {self._max_retries + 1} attempts "
                        f"({method} {versioned_path})"
                    ) from exc
                _backoff_sleep(attempt)
                continue
            except httpx.TransportError as exc:
                last_error = exc
                logger.warning(
                    "OpenAQ transport error method=%s path=%s attempt=%s/%s error=%s",
                    method,
                    versioned_path,
                    attempt,
                    self._max_retries + 1,
                    type(exc).__name__,
                )
                if attempt > self._max_retries:
                    raise OpenAQTransientError(
                        f"OpenAQ transport failure after {self._max_retries + 1} attempts "
                        f"({method} {versioned_path}): {type(exc).__name__}"
                    ) from exc
                _backoff_sleep(attempt)
                continue
            finally:
                self._last_request_monotonic = time.monotonic()

            duration_ms = int((time.monotonic() - started) * 1000)
            self._respect_rate_limit_headers(response)
            logger.info(
                "OpenAQ response method=%s path=%s status=%s duration_ms=%s "
                "attempt=%s rate_remaining=%s",
                method,
                versioned_path,
                response.status_code,
                duration_ms,
                attempt,
                response.headers.get("x-ratelimit-remaining"),
            )
            # Never log request headers — they contain X-API-Key.
            logger.debug(
                "OpenAQ response headers (redacted request not logged) path=%s meta_keys=%s",
                versioned_path,
                list(_redact_headers(response.headers).keys()),
            )

            if response.status_code in {401, 403}:
                raise OpenAQAuthError(
                    f"OpenAQ authentication failed with HTTP {response.status_code} "
                    f"for {method} {versioned_path}. Check OPENAQ_API_KEY."
                )

            if response.status_code == 429:
                retry_after = _parse_retry_after(response)
                logger.warning(
                    "OpenAQ rate limited path=%s retry_after_s=%s attempt=%s/%s",
                    versioned_path,
                    retry_after,
                    attempt,
                    self._max_retries + 1,
                )
                if attempt > self._max_retries:
                    raise OpenAQRateLimitError(
                        f"OpenAQ rate limit exceeded for {method} {versioned_path}",
                        retry_after_seconds=retry_after,
                    )
                time.sleep(retry_after if retry_after is not None else _backoff_seconds(attempt))
                continue

            if response.status_code in TRANSIENT_STATUS_CODES:
                logger.warning(
                    "OpenAQ transient HTTP %s path=%s attempt=%s/%s",
                    response.status_code,
                    versioned_path,
                    attempt,
                    self._max_retries + 1,
                )
                if attempt > self._max_retries:
                    raise OpenAQTransientError(
                        f"OpenAQ transient HTTP {response.status_code} after "
                        f"{self._max_retries + 1} attempts ({method} {versioned_path})"
                    )
                _backoff_sleep(attempt)
                continue

            if response.status_code >= 400:
                detail = _safe_error_body(response)
                raise OpenAQAPIError(
                    f"OpenAQ HTTP {response.status_code} for {method} {versioned_path}: {detail}",
                    status_code=response.status_code,
                    path=versioned_path,
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise OpenAQAPIError(
                    f"OpenAQ returned non-JSON body for {method} {versioned_path}",
                    status_code=response.status_code,
                    path=versioned_path,
                ) from exc

            if not isinstance(payload, dict):
                raise OpenAQAPIError(
                    f"OpenAQ JSON root must be an object for {versioned_path}",
                    status_code=response.status_code,
                    path=versioned_path,
                )
            return payload

        raise OpenAQTransientError(
            f"OpenAQ request failed after retries ({method} {versioned_path}): "
            f"{type(last_error).__name__ if last_error else 'unknown'}"
        )

    def _respect_rate_limit_headers(self, response: httpx.Response) -> None:
        """Pause when remaining quota is exhausted before the next call."""
        remaining_raw = response.headers.get("x-ratelimit-remaining")
        reset_raw = response.headers.get("x-ratelimit-reset")
        if remaining_raw is None:
            return
        try:
            remaining = int(remaining_raw)
        except ValueError:
            return
        if remaining > 0:
            return
        sleep_for = 1.0
        if reset_raw is not None:
            try:
                sleep_for = max(float(reset_raw), 1.0)
            except ValueError:
                sleep_for = 1.0
        logger.info(
            "OpenAQ rate-limit remaining=0; sleeping %.1fs before next request",
            sleep_for,
        )
        time.sleep(sleep_for)


def _format_openaq_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.astimezone().isoformat().replace("+00:00", "Z")


def _pages_exhausted(
    *,
    found: Any,
    page: int,
    limit: int,
    page_size: int,
) -> bool:
    if page_size < limit:
        return True
    if found is None:
        return page_size == 0
    if isinstance(found, str):
        # OpenAQ may return values like ">100" when totals are capped.
        digits = "".join(ch for ch in found if ch.isdigit())
        if not digits:
            return page_size < limit
        found_n = int(digits)
    else:
        try:
            found_n = int(found)
        except (TypeError, ValueError):
            return page_size < limit
    return page * limit >= found_n


def _parse_retry_after(response: httpx.Response) -> float | None:
    header = response.headers.get("Retry-After") or response.headers.get("x-ratelimit-reset")
    if header is None:
        return None
    try:
        return max(float(header), 0.0)
    except ValueError:
        return None


def _backoff_seconds(attempt: int) -> float:
    return min(2**attempt, 30)


def _backoff_sleep(attempt: int) -> None:
    time.sleep(_backoff_seconds(attempt))


def _safe_error_body(response: httpx.Response) -> str:
    try:
        data = response.json()
        return str(data)[:500]
    except Exception:  # noqa: BLE001 - best-effort diagnostics only
        return (response.text or "")[:500]


def build_absolute_url(base_url: str, path: str) -> str:
    """Helper for tests/docs — join base URL with a versioned path."""
    prefix = path if path.startswith(API_VERSION_PREFIX) else f"{API_VERSION_PREFIX}{path}"
    return urljoin(base_url.rstrip("/") + "/", prefix.lstrip("/"))
