"""Build a data-quality report from classified observations (observability)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from lahore_air_quality.quality.classify import classify_air_quality
from lahore_air_quality.quality.rules import (
    find_duplicate_keys,
    find_missing_intervals,
    inactive_stations,
    ingest_delay,
    is_delayed_ingest,
    is_stale,
)
from lahore_air_quality.quality.thresholds import (
    DELAYED_INGEST_AFTER,
    EXPECTED_AQ_INTERVAL,
    GAP_FACTOR,
    SENSOR_INACTIVE_AFTER,
    STALE_AFTER,
    canonical_pollutant,
)
from lahore_air_quality.quality.types import (
    AirQualityRecord,
    QualityClass,
    WeatherRecord,
)


@dataclass
class DataQualityReport:
    """Structured quality report — for logs, Dagster metadata, or API later."""

    generated_at: datetime
    record_counts: dict[str, int]
    duplicate_counts: dict[str, int]
    null_counts: dict[str, int]
    freshness: dict[str, Any]
    sensor_activity: dict[str, Any]
    value_extremes: dict[str, Any]
    missing_intervals: list[dict[str, Any]] = field(default_factory=list)
    rule_hit_counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["generated_at"] = self.generated_at.isoformat()
        return data


def build_air_quality_report(
    records: Sequence[AirQualityRecord],
    *,
    weather_hours: Iterable[datetime] | None = None,
    now: datetime | None = None,
) -> DataQualityReport:
    """Evaluate a batch of AQ rows and produce an observability report.

    Does **not** delete or rewrite observations — classification only.
    """
    clock = now or datetime.now(tz=UTC)
    weather_hour_set = {
        ts.replace(minute=0, second=0, microsecond=0) for ts in (weather_hours or [])
    }

    class_counts: Counter[str] = Counter()
    rule_hits: Counter[str] = Counter()
    null_counts = {
        "observed_at": 0,
        "value": 0,
        "pollutant": 0,
        "unit": 0,
        "station_id": 0,
    }
    values_by_pollutant: dict[str, list[Decimal]] = {}
    latest_by_station: dict[str, datetime] = {}
    timestamps: list[datetime] = []

    for record in records:
        if record.observed_at is None:
            null_counts["observed_at"] += 1
        if record.value is None:
            null_counts["value"] += 1
        if not record.pollutant:
            null_counts["pollutant"] += 1
        if not record.unit:
            null_counts["unit"] += 1
        if not record.station_id:
            null_counts["station_id"] += 1

        has_weather: bool | None = None
        if record.observed_at is not None and weather_hours is not None:
            hour = record.observed_at.replace(minute=0, second=0, microsecond=0)
            has_weather = hour in weather_hour_set

        result = classify_air_quality(record, now=clock, has_weather_for_hour=has_weather)
        class_counts[result.quality_class.value] += 1
        for finding in result.findings:
            rule_hits[finding.rule_id] += 1

        if record.observed_at is not None:
            timestamps.append(record.observed_at)
            if record.station_id:
                prev = latest_by_station.get(record.station_id)
                if prev is None or record.observed_at > prev:
                    latest_by_station[record.station_id] = record.observed_at

        code = canonical_pollutant(record.pollutant) if record.pollutant else None
        if code is not None and record.value is not None:
            try:
                values_by_pollutant.setdefault(code, []).append(Decimal(str(record.value)))
            except Exception:  # noqa: BLE001
                pass

    dup_keys = find_duplicate_keys(records)
    gaps = find_missing_intervals(
        timestamps,
        expected=EXPECTED_AQ_INTERVAL,
        gap_factor=GAP_FACTOR,
    )
    inactive = inactive_stations(latest_by_station, now=clock, inactive_after=SENSOR_INACTIVE_AFTER)
    latest = max(timestamps) if timestamps else None
    stale = is_stale(latest, now=clock, stale_after=STALE_AFTER)
    delayed_count = sum(
        1
        for r in records
        if is_delayed_ingest(r.observed_at, r.ingested_at, delayed_after=DELAYED_INGEST_AFTER)
    )
    max_ingest_lag_hours: float | None = None
    for r in records:
        delay = ingest_delay(r.observed_at, r.ingested_at)
        if delay is None:
            continue
        hours = delay.total_seconds() / 3600.0
        if max_ingest_lag_hours is None or hours > max_ingest_lag_hours:
            max_ingest_lag_hours = hours

    extremes: dict[str, Any] = {}
    for code, vals in values_by_pollutant.items():
        extremes[code] = {"min": float(min(vals)), "max": float(max(vals)), "n": len(vals)}

    notes = [
        "Suspicious and invalid rows are classified only — never deleted.",
        "See docs/data-quality.md for rule definitions.",
    ]
    if weather_hours is not None:
        notes.append("missing_weather evaluated against provided weather hour set.")

    return DataQualityReport(
        generated_at=clock,
        record_counts={
            "total": len(records),
            QualityClass.VALID.value: class_counts[QualityClass.VALID.value],
            QualityClass.SUSPECT.value: class_counts[QualityClass.SUSPECT.value],
            QualityClass.INVALID.value: class_counts[QualityClass.INVALID.value],
        },
        duplicate_counts={
            "duplicate_natural_keys": len(dup_keys),
            "rows_flagged_is_duplicate": sum(1 for r in records if r.is_duplicate),
        },
        null_counts=null_counts,
        freshness={
            "latest_observed_at": latest.isoformat() if latest else None,
            "lag_hours": (
                (clock - latest).total_seconds() / 3600.0 if latest is not None else None
            ),
            "stale": stale,
            "stale_after_hours": STALE_AFTER.total_seconds() / 3600.0,
            "delayed_ingest_count": delayed_count,
            "max_ingest_delay_hours": max_ingest_lag_hours,
            "delayed_ingest_after_hours": DELAYED_INGEST_AFTER.total_seconds() / 3600.0,
        },
        sensor_activity={
            "stations_seen": len(latest_by_station),
            "inactive_stations": inactive,
            "inactive_after_hours": SENSOR_INACTIVE_AFTER.total_seconds() / 3600.0,
        },
        value_extremes=extremes,
        missing_intervals=[
            {
                "from": a.isoformat(),
                "to": b.isoformat(),
                "gap_hours": round(hours, 3),
            }
            for a, b, hours in gaps
        ],
        rule_hit_counts=dict(rule_hits),
        notes=notes,
    )


def weather_hours_from_records(records: Iterable[WeatherRecord]) -> list[datetime]:
    hours: list[datetime] = []
    for r in records:
        if r.observed_at is not None:
            hours.append(r.observed_at.replace(minute=0, second=0, microsecond=0))
    return hours
