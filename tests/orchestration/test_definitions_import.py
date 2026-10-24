"""Smoke: Definitions module loads when Dagster is installed."""

from __future__ import annotations

import pytest

pytest.importorskip("dagster")


def test_definitions_load() -> None:
    from lahore_aqi_dagster.assets import ALL_ASSETS
    from lahore_aqi_dagster.definitions import defs
    from lahore_aqi_dagster.jobs import (
        dbt_only_job,
        full_pipeline_job,
        ingest_and_load_job,
    )

    assert defs is not None
    assert len(ALL_ASSETS) == 4
    assert ingest_and_load_job.name == "ingest_and_load_job"
    assert dbt_only_job.name == "dbt_only_job"
    assert full_pipeline_job.name == "full_pipeline_job"
