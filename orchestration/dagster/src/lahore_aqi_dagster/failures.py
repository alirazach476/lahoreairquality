"""Typed pipeline failures for visible, retry-aware Dagster runs.

Failure classes map to operational categories required by the platform:

- temporary API failure → retryable
- data validation failure → not retryable
- database failure → retryable
- transformation failure → not retryable (fix/seed/config issues need a fix)
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from dagster import Failure, MetadataValue


class FailureKind(StrEnum):
    TEMPORARY_API = "temporary_api_failure"
    DATA_VALIDATION = "data_validation_failure"
    DATABASE = "database_failure"
    TRANSFORMATION = "transformation_failure"


def _metadata(
    kind: FailureKind,
    *,
    stage: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "failure_kind": MetadataValue.text(kind.value),
        "stage": MetadataValue.text(stage),
        "retryable": MetadataValue.bool(kind in {FailureKind.TEMPORARY_API, FailureKind.DATABASE}),
    }
    if extra:
        for key, value in extra.items():
            if isinstance(value, bool):
                meta[key] = MetadataValue.bool(value)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                meta[key] = MetadataValue.float(float(value))
            else:
                meta[key] = MetadataValue.text(str(value))
    return meta


def raise_failure(
    kind: FailureKind,
    description: str,
    *,
    stage: str,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Raise a Dagster ``Failure`` with structured metadata (never returns)."""
    allow_retries = kind in {FailureKind.TEMPORARY_API, FailureKind.DATABASE}
    raise Failure(
        description=f"[{kind.value}] {description}",
        metadata=_metadata(kind, stage=stage, extra=extra),
        allow_retries=allow_retries,
    )


def temporary_api_failure(description: str, *, stage: str = "api_ingestion", **extra: Any) -> None:
    raise_failure(FailureKind.TEMPORARY_API, description, stage=stage, extra=extra)


def data_validation_failure(description: str, *, stage: str = "validation", **extra: Any) -> None:
    raise_failure(FailureKind.DATA_VALIDATION, description, stage=stage, extra=extra)


def database_failure(description: str, *, stage: str = "database", **extra: Any) -> None:
    raise_failure(FailureKind.DATABASE, description, stage=stage, extra=extra)


def transformation_failure(description: str, *, stage: str = "dbt", **extra: Any) -> None:
    raise_failure(FailureKind.TRANSFORMATION, description, stage=stage, extra=extra)
