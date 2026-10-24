"""Production data-quality monitoring against PostgreSQL observations.

Uses only real rows from ``raw.air_quality_observations`` /
``raw.weather_observations``. Never loads synthetic fixtures or invents values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from lahore_air_quality.db.health import DatabaseHealth, check_database_health
from lahore_air_quality.quality.classify import classify_weather
from lahore_air_quality.quality.load import (
    count_air_quality_rows,
    count_weather_rows,
    load_air_quality_records,
    load_weather_records,
    weather_hours,
)
from lahore_air_quality.quality.report import DataQualityReport, build_air_quality_report
from lahore_air_quality.quality.thresholds import (
    EXPECTED_AQ_INTERVAL,
    SENSOR_INACTIVE_AFTER,
    STALE_AFTER,
)
from lahore_air_quality.quality.types import QualityClass

MonitorStatus = Literal[
    "OK",
    "NO_DATA_AVAILABLE",
    "DATABASE_UNAVAILABLE",
]


@dataclass
class MonitorResult:
    """Outcome of a production monitoring run."""

    status: MonitorStatus
    message: str
    generated_at: datetime
    database: dict[str, Any] = field(default_factory=dict)
    table_counts: dict[str, int] = field(default_factory=dict)
    air_quality_report: DataQualityReport | None = None
    weather_class_counts: dict[str, int] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "message": self.message,
            "generated_at": self.generated_at.isoformat(),
            "database": self.database,
            "table_counts": self.table_counts,
            "weather_class_counts": self.weather_class_counts,
            "thresholds": self.thresholds,
            "notes": self.notes,
            "air_quality_report": (
                self.air_quality_report.as_dict() if self.air_quality_report else None
            ),
        }
        return payload


def run_data_quality_monitor(
    session: Session,
    *,
    now: datetime | None = None,
    observed_from: datetime | None = None,
    observed_to: datetime | None = None,
    database_health: DatabaseHealth | None = None,
) -> MonitorResult:
    """Evaluate quality rules on real DB observations.

    If AQ + weather tables are empty, returns ``NO_DATA_AVAILABLE`` without
    synthesizing data. Suspicious/invalid rows are classified only — never deleted.
    """
    clock = now or datetime.now(tz=UTC)
    health = database_health or check_database_health()
    thresholds = {
        "stale_after_hours": STALE_AFTER.total_seconds() / 3600.0,
        "sensor_inactive_after_hours": SENSOR_INACTIVE_AFTER.total_seconds() / 3600.0,
        "expected_aq_interval_hours": EXPECTED_AQ_INTERVAL.total_seconds() / 3600.0,
        "note": (
            "A sensor is inactive only when its latest observation is older than "
            "SENSOR_INACTIVE_AFTER (default 6h), which is longer than the expected "
            "hourly reporting interval — not merely a single missed hour."
        ),
    }
    notes = [
        "Production monitor reads raw.air_quality_observations and "
        "raw.weather_observations only — no synthetic fixtures.",
        "Suspicious/invalid rows are retained (never auto-deleted).",
        "Missing readings are left as null / absent — never treated as zero.",
        "See docs/data-quality.md for rule definitions.",
    ]

    if not health.healthy:
        return MonitorResult(
            status="DATABASE_UNAVAILABLE",
            message=health.message,
            generated_at=clock,
            database={
                "healthy": False,
                "message": health.message,
                "server_version": health.server_version,
            },
            thresholds=thresholds,
            notes=notes,
        )

    aq_count = count_air_quality_rows(session)
    wx_count = count_weather_rows(session)
    table_counts = {
        "raw.air_quality_observations": aq_count,
        "raw.weather_observations": wx_count,
    }

    if aq_count == 0 and wx_count == 0:
        return MonitorResult(
            status="NO_DATA_AVAILABLE",
            message=(
                "No air-quality or weather observations in PostgreSQL. "
                "Run the ingestion pipeline or "
                "`python -m ingestion.bootstrap_history --execute` after reviewing "
                "the import plan."
            ),
            generated_at=clock,
            database={
                "healthy": True,
                "message": health.message,
                "server_version": health.server_version,
            },
            table_counts=table_counts,
            thresholds=thresholds,
            notes=notes,
        )

    aq_records = load_air_quality_records(
        session, observed_from=observed_from, observed_to=observed_to
    )
    wx_records = load_weather_records(session, observed_from=observed_from, observed_to=observed_to)

    wx_classes: dict[str, int] = {
        QualityClass.VALID.value: 0,
        QualityClass.SUSPECT.value: 0,
        QualityClass.INVALID.value: 0,
    }
    for record in wx_records:
        result = classify_weather(record, now=clock)
        wx_classes[result.quality_class.value] += 1

    report: DataQualityReport | None = None
    if aq_records:
        report = build_air_quality_report(
            aq_records,
            weather_hours=weather_hours(wx_records) if wx_records else [],
            now=clock,
        )
    else:
        notes.append(
            "Air-quality table empty in the selected window; weather-only "
            "classification was computed."
        )

    return MonitorResult(
        status="OK",
        message=(
            f"Evaluated {len(aq_records)} air-quality and {len(wx_records)} "
            "weather observation(s) from PostgreSQL."
        ),
        generated_at=clock,
        database={
            "healthy": True,
            "message": health.message,
            "server_version": health.server_version,
        },
        table_counts=table_counts,
        air_quality_report=report,
        weather_class_counts=wx_classes,
        thresholds=thresholds,
        notes=notes,
    )
