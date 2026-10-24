"""Bootstrap defaults (date windows, pollutants). No hard-coded sensor IDs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

# Only request these pollutants when a discovered sensor actually measures them.
TARGET_POLLUTANTS: Final[frozenset[str]] = frozenset({"pm25", "pm10"})

# OpenAQ historical fetch chunk size (calendar days) to keep pagination bounded.
DEFAULT_AQ_CHUNK_DAYS: Final[int] = 3

# Default lookback when the operator does not pass explicit dates.
DEFAULT_LOOKBACK_DAYS: Final[int] = 7

# Target tables (existing schema — never invent new names).
TARGET_TABLES: Final[tuple[str, ...]] = (
    "raw.ingestion_payloads",
    "raw.air_quality_observations",
    "raw.weather_observations",
)

TARGET_TABLES_WEATHER_ONLY: Final[tuple[str, ...]] = (
    "raw.ingestion_payloads",
    "raw.weather_observations",
)

# Object storage prefix for original API JSON (existing consumer layout).
RAW_OBJECT_PREFIX: Final[str] = "raw/"

# Open-Meteo free/non-commercial attribution (CC BY 4.0).
OPEN_METEO_ATTRIBUTION: Final[str] = (
    "Weather data by Open-Meteo.com (https://open-meteo.com) — "
    "Historical Weather API / ERA5 reanalysis; CC BY 4.0. "
    "Model-derived, not ground-station measurements."
)


@dataclass(frozen=True, slots=True)
class BootstrapWindow:
    """Inclusive UTC window for historical import."""

    start: datetime
    end: datetime

    def as_dict(self) -> dict[str, str]:
        return {"start_utc": self.start.isoformat(), "end_utc": self.end.isoformat()}


def as_utc(value: datetime) -> datetime:
    """Normalize to timezone-aware UTC (naive values treated as UTC wall time)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def completed_utc_hour(*, now: datetime | None = None) -> datetime:
    """Current completed UTC hour (minutes/seconds truncated)."""
    clock = as_utc(now) if now is not None else datetime.now(tz=UTC)
    return clock.replace(minute=0, second=0, microsecond=0)


def effective_weather_persist_end(
    requested_end: datetime,
    *,
    now: datetime | None = None,
) -> datetime:
    """Latest ``observed_at`` allowed when persisting historical weather.

    Open-Meteo archive requests use calendar ``end_date`` and may return every
    hour of that day, including hours later than wall-clock. Persist only
    through ``min(requested_end, completed_utc_hour)``.
    """
    return min(as_utc(requested_end), completed_utc_hour(now=now))


def is_within_bootstrap_window(
    observed_at: datetime | None,
    window: BootstrapWindow,
) -> bool:
    """True when ``observed_at`` lies in ``[window.start, window.end]`` (UTC inclusive).

    Naive datetimes are interpreted as UTC wall time (same convention as
    :func:`as_utc`). ``None`` or non-datetime values are out of window.
    """
    if observed_at is None or not isinstance(observed_at, datetime):
        return False
    observed = as_utc(observed_at)
    start = as_utc(window.start)
    end = as_utc(window.end)
    return start <= observed <= end


def default_window(*, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> BootstrapWindow:
    end = completed_utc_hour()
    start = end - timedelta(days=lookback_days)
    return BootstrapWindow(start=start, end=end)


def iter_chunks(
    window: BootstrapWindow, *, chunk_days: int = DEFAULT_AQ_CHUNK_DAYS
) -> list[BootstrapWindow]:
    if chunk_days < 1:
        raise ValueError("chunk_days must be >= 1")
    chunks: list[BootstrapWindow] = []
    cursor = window.start
    delta = timedelta(days=chunk_days)
    while cursor < window.end:
        nxt = min(cursor + delta, window.end)
        chunks.append(BootstrapWindow(start=cursor, end=nxt))
        cursor = nxt
    return chunks
