"""Failure classification helpers."""

from __future__ import annotations

import pytest
from dagster import Failure

from lahore_aqi_dagster.failures import (
    FailureKind,
    data_validation_failure,
    database_failure,
    temporary_api_failure,
    transformation_failure,
)


def test_temporary_api_failure_is_retryable() -> None:
    with pytest.raises(Failure) as exc_info:
        temporary_api_failure("upstream down", stage="api_ingestion")
    failure = exc_info.value
    assert failure.allow_retries is True
    assert FailureKind.TEMPORARY_API.value in (failure.description or "")


def test_validation_and_transform_are_not_retryable() -> None:
    with pytest.raises(Failure) as exc_info:
        data_validation_failure("bad payload", stage="validation")
    assert exc_info.value.allow_retries is False

    with pytest.raises(Failure) as exc_info:
        transformation_failure("dbt failed", stage="dbt_run")
    assert exc_info.value.allow_retries is False


def test_database_failure_is_retryable() -> None:
    with pytest.raises(Failure) as exc_info:
        database_failure("connection refused", stage="database")
    assert exc_info.value.allow_retries is True
