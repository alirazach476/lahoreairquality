"""Open-Meteo weather client (Forecast + Historical Archive APIs).

Docs:
- https://open-meteo.com/en/docs
- https://open-meteo.com/en/docs/historical-weather-api

No API key is required for the public endpoints. Lahore coordinates come from
configuration (``LAHORE_LATITUDE`` / ``LAHORE_LONGITUDE``), not scattered
hard-coded values in call sites.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx

from lahore_aqi_poller.clients.openmeteo.constants import (
    ARCHIVE_PATH,
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_FORECAST_DAYS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PAST_DAYS,
    DEFAULT_TIMEOUT_SECONDS,
    FORECAST_PATH,
    HOURLY_VARIABLES,
    TIMEZONE,
    TRANSIENT_STATUS_CODES,
    WIND_SPEED_UNIT,
)
from lahore_aqi_poller.clients.openmeteo.exceptions import (
    OpenMeteoAPIError,
    OpenMeteoConfigError,
    OpenMeteoRateLimitError,
    OpenMeteoTransientError,
)
from lahore_aqi_poller.clients.openmeteo.models import (
    GeoPoint,
    WeatherObservationBundle,
)
from lahore_aqi_poller.clients.openmeteo.normalize import (
    normalize_current,
    normalize_hourly,
)

logger = logging.getLogger(__name__)


class OpenMeteoClient:
    """Reusable HTTP client for Open-Meteo forecast, current, and archive data."""

    def __init__(
        self,
        *,
        latitude: float,
        longitude: float,
        forecast_base_url: str = "https://api.open-meteo.com",
        archive_base_url: str = "https://archive-api.open-meteo.com",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        try:
            self._point = GeoPoint(latitude=latitude, longitude=longitude)
        except Exception as exc:
            raise OpenMeteoConfigError(f"Invalid Lahore/geo coordinates: {exc}") from exc

        self._forecast_base_url = forecast_base_url.rstrip("/")
        self._archive_base_url = archive_base_url.rstrip("/")
        self._max_retries = max_retries

        timeout = httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds)
        # One client; absolute URLs are used so forecast vs archive hosts work.
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": "lahore-air-quality-openmeteo-client/0.1",
            },
            transport=transport,
            follow_redirects=True,
        )

    @classmethod
    def from_settings(cls, settings: Any | None = None) -> OpenMeteoClient:
        """Build a client using configurable Lahore coordinates and base URLs."""
        if settings is None:
            from lahore_air_quality.config import get_settings

            settings = get_settings()
        return cls(
            latitude=settings.lahore_latitude,
            longitude=settings.lahore_longitude,
            forecast_base_url=settings.openmeteo_base_url,
            archive_base_url=settings.openmeteo_archive_base_url,
        )

    @property
    def coordinates(self) -> GeoPoint:
        """Configured target coordinates (typically Lahore)."""
        return self._point

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenMeteoClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Public fetch APIs
    # ------------------------------------------------------------------

    def fetch_forecast_raw(
        self,
        *,
        forecast_days: int = DEFAULT_FORECAST_DAYS,
        past_days: int = DEFAULT_PAST_DAYS,
        include_current: bool = True,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> dict[str, Any]:
        """Fetch raw Forecast API JSON (hourly + optional current)."""
        lat, lon = self._resolve_point(latitude, longitude)
        if not 0 <= forecast_days <= 16:
            raise ValueError("forecast_days must be between 0 and 16")
        if not 0 <= past_days <= 92:
            raise ValueError("past_days must be between 0 and 92")

        params: dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(HOURLY_VARIABLES),
            "forecast_days": forecast_days,
            "past_days": past_days,
            "timezone": TIMEZONE,
            "wind_speed_unit": WIND_SPEED_UNIT,
        }
        if include_current:
            params["current"] = ",".join(HOURLY_VARIABLES)

        url = f"{self._forecast_base_url}{FORECAST_PATH}"
        logger.info(
            "Fetching Open-Meteo forecast lat=%s lon=%s forecast_days=%s past_days=%s",
            lat,
            lon,
            forecast_days,
            past_days,
        )
        return self._request_json(url, params=params)

    def fetch_current(
        self,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> WeatherObservationBundle | None:
        """Fetch and normalize current weather for the configured point."""
        lat, lon = self._resolve_point(latitude, longitude)
        raw = self.fetch_forecast_raw(
            forecast_days=1,
            past_days=0,
            include_current=True,
            latitude=lat,
            longitude=lon,
        )
        return normalize_current(
            raw,
            request_latitude=lat,
            request_longitude=lon,
        )

    def fetch_forecast(
        self,
        *,
        forecast_days: int = DEFAULT_FORECAST_DAYS,
        past_days: int = DEFAULT_PAST_DAYS,
        include_current: bool = True,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> list[WeatherObservationBundle]:
        """Fetch forecast/recent hourly weather and normalize observations.

        When ``include_current`` is true and a current block is present, the
        current observation is prepended (hourly series still returned fully).
        """
        lat, lon = self._resolve_point(latitude, longitude)
        raw = self.fetch_forecast_raw(
            forecast_days=forecast_days,
            past_days=past_days,
            include_current=include_current,
            latitude=lat,
            longitude=lon,
        )
        bundles = normalize_hourly(
            raw,
            request_latitude=lat,
            request_longitude=lon,
            kind="forecast_hourly",
        )
        if include_current:
            current = normalize_current(
                raw,
                request_latitude=lat,
                request_longitude=lon,
            )
            if current is not None:
                bundles = [current, *bundles]
        return bundles

    def fetch_historical_raw(
        self,
        *,
        start_date: date,
        end_date: date,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> dict[str, Any]:
        """Fetch raw Historical Weather API JSON for a date range."""
        lat, lon = self._resolve_point(latitude, longitude)
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        params: dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": ",".join(HOURLY_VARIABLES),
            "timezone": TIMEZONE,
            "wind_speed_unit": WIND_SPEED_UNIT,
        }
        url = f"{self._archive_base_url}{ARCHIVE_PATH}"
        logger.info(
            "Fetching Open-Meteo archive lat=%s lon=%s start=%s end=%s",
            lat,
            lon,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        return self._request_json(url, params=params)

    def fetch_historical(
        self,
        *,
        start_date: date,
        end_date: date,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> list[WeatherObservationBundle]:
        """Fetch and normalize historical hourly weather observations."""
        lat, lon = self._resolve_point(latitude, longitude)
        raw = self.fetch_historical_raw(
            start_date=start_date,
            end_date=end_date,
            latitude=lat,
            longitude=lon,
        )
        return normalize_hourly(
            raw,
            request_latitude=lat,
            request_longitude=lon,
            kind="historical_hourly",
        )

    def fetch_historical_for_datetimes(
        self,
        *,
        datetime_from: datetime,
        datetime_to: datetime,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> list[WeatherObservationBundle]:
        """Historical helper accepting datetimes (converted to UTC calendar dates)."""
        if datetime_to < datetime_from:
            raise ValueError("datetime_to must be on or after datetime_from")

        start_dt = (
            datetime_from.astimezone(UTC)
            if datetime_from.tzinfo is not None
            else datetime_from.replace(tzinfo=UTC)
        )
        end_dt = (
            datetime_to.astimezone(UTC)
            if datetime_to.tzinfo is not None
            else datetime_to.replace(tzinfo=UTC)
        )
        return self.fetch_historical(
            start_date=start_dt.date(),
            end_date=end_dt.date(),
            latitude=latitude,
            longitude=longitude,
        )

    @staticmethod
    def normalize_response(
        raw_response: dict[str, Any],
        *,
        request_latitude: float,
        request_longitude: float,
        kind: str = "hourly",
        include_current: bool = False,
    ) -> list[WeatherObservationBundle]:
        """Normalize a raw Open-Meteo JSON payload into observation bundles."""
        bundles = normalize_hourly(
            raw_response,
            request_latitude=request_latitude,
            request_longitude=request_longitude,
            kind=kind,
        )
        if include_current:
            current = normalize_current(
                raw_response,
                request_latitude=request_latitude,
                request_longitude=request_longitude,
            )
            if current is not None:
                bundles = [current, *bundles]
        return bundles

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_point(
        self, latitude: float | None, longitude: float | None
    ) -> tuple[float, float]:
        if latitude is None and longitude is None:
            return self._point.latitude, self._point.longitude
        if latitude is None or longitude is None:
            raise OpenMeteoConfigError(
                "latitude and longitude must both be provided when overriding"
            )
        point = GeoPoint(latitude=latitude, longitude=longitude)
        return point.latitude, point.longitude

    def _request_json(self, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
        attempt = 0
        last_error: Exception | None = None

        while attempt <= self._max_retries:
            attempt += 1
            started = time.monotonic()
            try:
                response = self._client.get(url, params=params)
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "Open-Meteo timeout url=%s attempt=%s/%s error=%s",
                    url,
                    attempt,
                    self._max_retries + 1,
                    type(exc).__name__,
                )
                if attempt > self._max_retries:
                    raise OpenMeteoTransientError(
                        f"Open-Meteo request timed out after {self._max_retries + 1} "
                        f"attempts ({url})"
                    ) from exc
                _backoff_sleep(attempt)
                continue
            except httpx.TransportError as exc:
                last_error = exc
                logger.warning(
                    "Open-Meteo transport error url=%s attempt=%s/%s error=%s",
                    url,
                    attempt,
                    self._max_retries + 1,
                    type(exc).__name__,
                )
                if attempt > self._max_retries:
                    raise OpenMeteoTransientError(
                        f"Open-Meteo transport failure after {self._max_retries + 1} "
                        f"attempts ({url}): {type(exc).__name__}"
                    ) from exc
                _backoff_sleep(attempt)
                continue

            duration_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "Open-Meteo response url_path=%s status=%s duration_ms=%s attempt=%s",
                httpx.URL(url).path,
                response.status_code,
                duration_ms,
                attempt,
            )

            if response.status_code == 429:
                retry_after = _parse_retry_after(response)
                logger.warning(
                    "Open-Meteo rate limited path=%s retry_after_s=%s attempt=%s/%s",
                    httpx.URL(url).path,
                    retry_after,
                    attempt,
                    self._max_retries + 1,
                )
                if attempt > self._max_retries:
                    raise OpenMeteoRateLimitError(
                        f"Open-Meteo rate limit exceeded for {url}",
                        retry_after_seconds=retry_after,
                    )
                time.sleep(retry_after if retry_after is not None else _backoff_seconds(attempt))
                continue

            if response.status_code in TRANSIENT_STATUS_CODES:
                logger.warning(
                    "Open-Meteo transient HTTP %s path=%s attempt=%s/%s",
                    response.status_code,
                    httpx.URL(url).path,
                    attempt,
                    self._max_retries + 1,
                )
                if attempt > self._max_retries:
                    raise OpenMeteoTransientError(
                        f"Open-Meteo transient HTTP {response.status_code} after "
                        f"{self._max_retries + 1} attempts ({url})"
                    )
                _backoff_sleep(attempt)
                continue

            if response.status_code >= 400:
                detail = _safe_error_body(response)
                raise OpenMeteoAPIError(
                    f"Open-Meteo HTTP {response.status_code} for {url}: {detail}",
                    status_code=response.status_code,
                    path=httpx.URL(url).path,
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise OpenMeteoAPIError(
                    f"Open-Meteo returned non-JSON body for {url}",
                    status_code=response.status_code,
                    path=httpx.URL(url).path,
                ) from exc

            if not isinstance(payload, dict):
                raise OpenMeteoAPIError(
                    f"Open-Meteo JSON root must be an object for {url}",
                    status_code=response.status_code,
                    path=httpx.URL(url).path,
                )

            # Open-Meteo returns {"reason": "...", "error": true} on some failures
            # with HTTP 200 in older behaviour; still handle explicitly.
            if payload.get("error") is True:
                reason = str(payload.get("reason") or "unknown error")
                raise OpenMeteoAPIError(
                    f"Open-Meteo API error for {url}: {reason}",
                    path=httpx.URL(url).path,
                )

            return payload

        raise OpenMeteoTransientError(
            f"Open-Meteo request failed after retries ({url}): "
            f"{type(last_error).__name__ if last_error else 'unknown'}"
        )


def _backoff_seconds(attempt: int) -> float:
    return min(2**attempt, 30)


def _backoff_sleep(attempt: int) -> None:
    time.sleep(_backoff_seconds(attempt))


def _parse_retry_after(response: httpx.Response) -> float | None:
    header = response.headers.get("Retry-After")
    if header is None:
        return None
    try:
        return max(float(header), 0.0)
    except ValueError:
        return None


def _safe_error_body(response: httpx.Response) -> str:
    try:
        data = response.json()
        return str(data)[:500]
    except Exception:  # noqa: BLE001 - best-effort diagnostics only
        return (response.text or "")[:500]
