"""OpenAQ client exception hierarchy."""

from __future__ import annotations


class OpenAQError(Exception):
    """Base error for OpenAQ client failures."""


class OpenAQConfigError(OpenAQError):
    """Missing or invalid client configuration (e.g. API key)."""


class OpenAQAuthError(OpenAQError):
    """Authentication or authorization failure (HTTP 401/403)."""


class OpenAQRateLimitError(OpenAQError):
    """Rate limit exceeded after retries (HTTP 429)."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class OpenAQAPIError(OpenAQError):
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


class OpenAQTransientError(OpenAQError):
    """Transient network or server failure after retries are exhausted."""
