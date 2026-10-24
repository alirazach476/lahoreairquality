"""Tunables for orchestration stages (non-secret)."""

from __future__ import annotations

import os
from pathlib import Path

from dagster import ConfigurableResource


def _repo_root() -> Path:
    # orchestration/dagster/src/lahore_aqi_dagster/resources/pipeline.py → repo root
    return Path(__file__).resolve().parents[5]


class PipelineConfigResource(ConfigurableResource):
    """Local/dev knobs for bounded consumer drains and dbt paths."""

    consumer_max_messages: int = 200
    consumer_idle_polls: int = 5
    dbt_project_dir: str = ""
    dbt_profiles_dir: str = ""
    skip_dbt_if_unavailable: bool = True

    def resolved_consumer_max_messages(self) -> int:
        raw = os.environ.get("DAGSTER_CONSUMER_MAX_MESSAGES")
        if raw:
            return max(1, int(raw))
        return max(1, int(self.consumer_max_messages))

    def resolved_dbt_project_dir(self) -> Path:
        if self.dbt_project_dir.strip():
            return Path(self.dbt_project_dir).expanduser().resolve()
        env = os.environ.get("DBT_PROJECT_DIR")
        if env:
            return Path(env).expanduser().resolve()
        return (_repo_root() / "dbt" / "lahore_air_quality").resolve()

    def resolved_dbt_profiles_dir(self) -> Path:
        if self.dbt_profiles_dir.strip():
            return Path(self.dbt_profiles_dir).expanduser().resolve()
        env = os.environ.get("DBT_PROFILES_DIR")
        if env:
            return Path(env).expanduser().resolve()
        return self.resolved_dbt_project_dir()
