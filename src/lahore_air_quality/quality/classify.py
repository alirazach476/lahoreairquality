"""Aggregate rule findings into valid / suspect / invalid (no deletes)."""

from __future__ import annotations

from datetime import UTC, datetime

from lahore_air_quality.quality import rules
from lahore_air_quality.quality.types import (
    AirQualityRecord,
    ClassificationResult,
    QualityClass,
    RuleFinding,
    Severity,
    WeatherRecord,
)


def _rollup(findings: list[RuleFinding]) -> ClassificationResult:
    if any(f.severity is Severity.INVALID for f in findings):
        quality = QualityClass.INVALID
    elif findings:
        quality = QualityClass.SUSPECT
    else:
        quality = QualityClass.VALID
    return ClassificationResult(quality_class=quality, findings=tuple(findings))


def classify_air_quality(
    record: AirQualityRecord,
    *,
    now: datetime | None = None,
    has_weather_for_hour: bool | None = None,
) -> ClassificationResult:
    """Classify one AQ observation. Never mutates or deletes source data."""
    clock = now or datetime.now(tz=UTC)
    findings: list[RuleFinding] = []
    findings.extend(rules.rule_missing_timestamp(record))
    findings.extend(rules.rule_missing_value(record))
    findings.extend(rules.rule_future_timestamp(record, now=clock))
    findings.extend(rules.rule_delayed_ingest(record))
    findings.extend(rules.rule_unexpected_pollutant(record))
    findings.extend(rules.rule_unexpected_unit(record))
    findings.extend(rules.rule_negative_concentration(record))
    findings.extend(rules.rule_abnormal_value(record))
    findings.extend(rules.rule_duplicate_observation(record))

    if has_weather_for_hour is False:
        findings.append(
            RuleFinding(
                "missing_weather",
                Severity.SUSPECT,
                "no weather observation for the same UTC hour",
            )
        )

    return _rollup(findings)


def classify_weather(
    record: WeatherRecord,
    *,
    now: datetime | None = None,
) -> ClassificationResult:
    """Classify one weather observation. Never mutates or deletes source data."""
    clock = now or datetime.now(tz=UTC)
    findings: list[RuleFinding] = []
    findings.extend(rules.rule_weather_missing_timestamp(record))
    findings.extend(rules.rule_weather_future_timestamp(record, now=clock))
    findings.extend(rules.rule_weather_range(record))
    findings.extend(rules.rule_weather_duplicate(record))
    return _rollup(findings)
