"""Types for data-quality classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class QualityClass(StrEnum):
    """Record disposition — suspicious rows are retained, never deleted."""

    VALID = "valid"
    SUSPECT = "suspect"
    INVALID = "invalid"


class Severity(StrEnum):
    SUSPECT = "suspect"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class RuleFinding:
    rule_id: str
    severity: Severity
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    quality_class: QualityClass
    findings: tuple[RuleFinding, ...]

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(f.rule_id for f in self.findings)


@dataclass(frozen=True, slots=True)
class AirQualityRecord:
    """Minimal AQ observation for quality evaluation."""

    station_id: str | None
    pollutant: str | None
    value: Decimal | float | int | None
    unit: str | None
    observed_at: datetime | None
    ingested_at: datetime | None = None
    source: str | None = None
    raw_record_id: str | None = None
    is_duplicate: bool = False


@dataclass(frozen=True, slots=True)
class WeatherRecord:
    latitude: float | None
    longitude: float | None
    observed_at: datetime | None
    temperature_c: Decimal | float | int | None = None
    relative_humidity_pct: Decimal | float | int | None = None
    precipitation_mm: Decimal | float | int | None = None
    wind_speed_ms: Decimal | float | int | None = None
    wind_direction_deg: Decimal | float | int | None = None
    pressure_hpa: Decimal | float | int | None = None
    ingested_at: datetime | None = None
    source: str | None = None
    is_duplicate: bool = False
