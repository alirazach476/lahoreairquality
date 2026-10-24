"""Individual data-quality rules (pure functions, independently testable)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from lahore_air_quality.quality.thresholds import (
    AQ_INVALID_CEILING,
    AQ_SUSPECT_CEILING,
    DELAYED_INGEST_AFTER,
    EXPECTED_UNITS,
    FUTURE_INVALID_TOLERANCE,
    FUTURE_SUSPECT_TOLERANCE,
    WEATHER_RANGES,
    canonical_pollutant,
    known_pollutant_codes,
)
from lahore_air_quality.quality.types import (
    AirQualityRecord,
    RuleFinding,
    Severity,
    WeatherRecord,
)


def _dec(value: Decimal | float | int | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Air-quality row rules
# ---------------------------------------------------------------------------


def rule_missing_timestamp(record: AirQualityRecord) -> list[RuleFinding]:
    if record.observed_at is None:
        return [
            RuleFinding(
                "missing_timestamp",
                Severity.INVALID,
                "observed_at is missing",
            )
        ]
    return []


def rule_future_timestamp(
    record: AirQualityRecord,
    *,
    now: datetime,
) -> list[RuleFinding]:
    if record.observed_at is None:
        return []
    obs = record.observed_at
    if obs.tzinfo is None and now.tzinfo is not None:
        # Compare naive as UTC wall time when tz missing.
        pass
    delta = obs - now
    if delta > FUTURE_INVALID_TOLERANCE:
        return [
            RuleFinding(
                "future_timestamp",
                Severity.INVALID,
                f"observed_at is more than {FUTURE_INVALID_TOLERANCE} in the future",
                {"delta_seconds": delta.total_seconds()},
            )
        ]
    if delta > FUTURE_SUSPECT_TOLERANCE:
        return [
            RuleFinding(
                "future_timestamp",
                Severity.SUSPECT,
                f"observed_at is slightly in the future (>{FUTURE_SUSPECT_TOLERANCE})",
                {"delta_seconds": delta.total_seconds()},
            )
        ]
    return []


def rule_negative_concentration(record: AirQualityRecord) -> list[RuleFinding]:
    value = _dec(record.value)
    if value is not None and value < 0:
        return [
            RuleFinding(
                "negative_concentration",
                Severity.INVALID,
                "concentration is negative",
                {"value": str(value)},
            )
        ]
    return []


def rule_unexpected_pollutant(record: AirQualityRecord) -> list[RuleFinding]:
    if record.pollutant is None or str(record.pollutant).strip() == "":
        return [
            RuleFinding(
                "unexpected_pollutant",
                Severity.INVALID,
                "pollutant name is missing",
            )
        ]
    code = canonical_pollutant(str(record.pollutant))
    if code is None:
        return [
            RuleFinding(
                "unexpected_pollutant",
                Severity.INVALID,
                f"pollutant {record.pollutant!r} is not a recognized canonical name",
            )
        ]
    return []


def rule_unexpected_unit(record: AirQualityRecord) -> list[RuleFinding]:
    if record.pollutant is None or record.unit is None:
        return []
    code = canonical_pollutant(str(record.pollutant))
    if code is None:
        return []
    allowed = EXPECTED_UNITS.get(code, frozenset())
    unit = record.unit.strip()
    if unit.lower() not in {u.lower() for u in allowed} and unit not in allowed:
        return [
            RuleFinding(
                "unexpected_unit",
                Severity.INVALID,
                f"unit {record.unit!r} is not valid for pollutant {code}",
                {"expected": sorted(allowed)},
            )
        ]
    return []


def rule_abnormal_value(record: AirQualityRecord) -> list[RuleFinding]:
    value = _dec(record.value)
    if value is None or record.pollutant is None:
        return []
    code = canonical_pollutant(str(record.pollutant))
    if code is None:
        return []
    invalid_hi = AQ_INVALID_CEILING.get(code)
    suspect_hi = AQ_SUSPECT_CEILING.get(code)
    if invalid_hi is not None and value > invalid_hi:
        return [
            RuleFinding(
                "abnormal_value",
                Severity.INVALID,
                f"{code} value {value} exceeds physical ceiling {invalid_hi}",
            )
        ]
    if suspect_hi is not None and value > suspect_hi:
        return [
            RuleFinding(
                "abnormal_value",
                Severity.SUSPECT,
                f"{code} value {value} is above EPA AQI≤500 range ({suspect_hi})",
            )
        ]
    return []


def rule_duplicate_observation(record: AirQualityRecord) -> list[RuleFinding]:
    if record.is_duplicate:
        return [
            RuleFinding(
                "duplicate_observation",
                Severity.SUSPECT,
                "observation matches an existing natural key (retained, not deleted)",
            )
        ]
    return []


def rule_missing_value(record: AirQualityRecord) -> list[RuleFinding]:
    if record.value is None:
        return [
            RuleFinding(
                "missing_value",
                Severity.INVALID,
                "concentration value is missing",
            )
        ]
    if _dec(record.value) is None:
        return [
            RuleFinding(
                "missing_value",
                Severity.INVALID,
                "concentration value is not numeric",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Weather row rules
# ---------------------------------------------------------------------------


def rule_weather_missing_timestamp(record: WeatherRecord) -> list[RuleFinding]:
    if record.observed_at is None:
        return [
            RuleFinding(
                "missing_timestamp",
                Severity.INVALID,
                "weather observed_at is missing",
            )
        ]
    return []


def rule_weather_future_timestamp(record: WeatherRecord, *, now: datetime) -> list[RuleFinding]:
    # Reuse AQ logic via a thin adapter.
    aq = AirQualityRecord(
        station_id=None,
        pollutant="pm25",
        value=0,
        unit="µg/m³",
        observed_at=record.observed_at,
    )
    return rule_future_timestamp(aq, now=now)


def rule_weather_range(record: WeatherRecord) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    fields = {
        "temperature_c": record.temperature_c,
        "relative_humidity_pct": record.relative_humidity_pct,
        "precipitation_mm": record.precipitation_mm,
        "wind_speed_ms": record.wind_speed_ms,
        "wind_direction_deg": record.wind_direction_deg,
        "pressure_hpa": record.pressure_hpa,
    }
    for name, raw in fields.items():
        value = _dec(raw)
        if value is None:
            continue
        low, high = WEATHER_RANGES[name]
        if value < low or value > high:
            findings.append(
                RuleFinding(
                    "abnormal_value",
                    Severity.INVALID,
                    f"weather {name}={value} outside [{low}, {high}]",
                )
            )
    return findings


def rule_weather_duplicate(record: WeatherRecord) -> list[RuleFinding]:
    if record.is_duplicate:
        return [
            RuleFinding(
                "duplicate_observation",
                Severity.SUSPECT,
                "weather observation is a duplicate natural key (retained)",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Set / report-level helpers
# ---------------------------------------------------------------------------


def find_duplicate_keys(
    records: Iterable[AirQualityRecord],
) -> list[tuple[str, str, str, datetime]]:
    """Return natural keys that appear more than once."""
    counts: dict[tuple[str, str, str, datetime], int] = {}
    for r in records:
        if r.observed_at is None or r.station_id is None or r.pollutant is None:
            continue
        key = (
            (r.source or ""),
            r.station_id,
            str(canonical_pollutant(r.pollutant) or r.pollutant),
            r.observed_at,
        )
        counts[key] = counts.get(key, 0) + 1
    return [k for k, n in counts.items() if n > 1]


def find_missing_intervals(
    timestamps: list[datetime],
    *,
    expected: timedelta,
    gap_factor: float,
) -> list[tuple[datetime, datetime, float]]:
    """Return (prev, next, gap_hours) for gaps larger than factor × expected."""
    if len(timestamps) < 2:
        return []
    ordered = sorted(timestamps)
    threshold = expected * gap_factor
    gaps: list[tuple[datetime, datetime, float]] = []
    for prev, nxt in zip(ordered, ordered[1:], strict=False):
        gap = nxt - prev
        if gap > threshold:
            gaps.append((prev, nxt, gap.total_seconds() / 3600.0))
    return gaps


def inactive_stations(
    latest_by_station: dict[str, datetime],
    *,
    now: datetime,
    inactive_after: timedelta,
) -> list[str]:
    return [station for station, ts in latest_by_station.items() if now - ts > inactive_after]


def is_stale(latest: datetime | None, *, now: datetime, stale_after: timedelta) -> bool:
    if latest is None:
        return True
    return now - latest > stale_after


def ingest_delay(observed_at: datetime | None, ingested_at: datetime | None) -> timedelta | None:
    """Return ``ingested_at − observed_at`` when both timestamps are present."""
    if observed_at is None or ingested_at is None:
        return None
    return ingested_at - observed_at


def is_delayed_ingest(
    observed_at: datetime | None,
    ingested_at: datetime | None,
    *,
    delayed_after: timedelta = DELAYED_INGEST_AFTER,
) -> bool:
    delay = ingest_delay(observed_at, ingested_at)
    if delay is None:
        return False
    return delay > delayed_after


def rule_delayed_ingest(
    record: AirQualityRecord,
    *,
    delayed_after: timedelta = DELAYED_INGEST_AFTER,
) -> list[RuleFinding]:
    """Flag late pipeline arrival (observation older than ingest by threshold).

    Delayed events are still retained — this is observability, not a drop.
    """
    delay = ingest_delay(record.observed_at, record.ingested_at)
    if delay is None or delay <= delayed_after:
        return []
    hours = delay.total_seconds() / 3600.0
    return [
        RuleFinding(
            "delayed_ingest",
            Severity.SUSPECT,
            f"ingested {hours:.1f}h after observed_at (threshold {delayed_after})",
            detail={
                "delay_hours": round(hours, 3),
                "delayed_after_hours": delayed_after.total_seconds() / 3600.0,
            },
        )
    ]


# Re-export for tests that assert known pollutant set.
KNOWN_POLLUTANTS = known_pollutant_codes
