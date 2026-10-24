"""Open-Meteo client exception hierarchy."""

from __future__ import annotations


class OpenMeteoError(Exception):
    """Base error for Open-Meteo client failures."""


class OpenMeteoConfigError(OpenMeteoError):
    """Missing or invalid client configuration."""


class OpenMeteoAPIError(OpenMeteoError):
    """Non-retryable or exhausted API error response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.path = path


class OpenMeteoTransientError(OpenMeteoError):
    """Transient network or server failure after retries are exhausted."""


class OpenMeteoRateLimitError(OpenMeteoError):
    """Rate limit exceeded after retries (HTTP 429)."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
