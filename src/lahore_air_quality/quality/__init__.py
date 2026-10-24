"""Data-quality classification and reporting (never deletes observations).

Rules and severity: ``docs/data-quality.md``.
"""

from lahore_air_quality.quality.classify import (
    classify_air_quality,
    classify_weather,
)
from lahore_air_quality.quality.monitor import MonitorResult, run_data_quality_monitor
from lahore_air_quality.quality.report import (
    DataQualityReport,
    build_air_quality_report,
)
from lahore_air_quality.quality.types import (
    AirQualityRecord,
    ClassificationResult,
    QualityClass,
    RuleFinding,
    WeatherRecord,
)

__all__ = [
    "AirQualityRecord",
    "ClassificationResult",
    "DataQualityReport",
    "MonitorResult",
    "QualityClass",
    "RuleFinding",
    "WeatherRecord",
    "build_air_quality_report",
    "classify_air_quality",
    "classify_weather",
    "run_data_quality_monitor",
]
