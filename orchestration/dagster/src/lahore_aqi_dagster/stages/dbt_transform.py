"""Stage 4–5: dbt transform + data-quality tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lahore_aqi_dagster.resources.dbt import DbtResource, DbtRunResult


@dataclass(frozen=True, slots=True)
class DbtStageResult:
    seed: dict[str, Any]
    run: dict[str, Any]
    test: dict[str, Any] | None = None


def _result_dict(result: DbtRunResult) -> dict[str, Any]:
    return {
        "command": list(result.command),
        "returncode": result.returncode,
        "skipped": result.skipped,
        "stdout_tail": result.stdout[-1000:],
        "stderr_tail": result.stderr[-500:],
    }


def run_dbt_transform(dbt: DbtResource) -> DbtStageResult:
    """``dbt seed`` then ``dbt run`` (transformation failure on non-zero exit)."""
    seed = dbt.execute(["seed"], stage="dbt_seed")
    run = dbt.execute(["run"], stage="dbt_run")
    return DbtStageResult(seed=_result_dict(seed), run=_result_dict(run))


def run_dbt_tests(dbt: DbtResource) -> dict[str, Any]:
    """``dbt test`` (hard fail) + ``dbt source freshness`` (soft — logged only)."""
    test = dbt.execute(["test"], stage="dbt_test")
    # Freshness can fail on lag without meaning the transform is broken.
    freshness = dbt.execute(
        ["source", "freshness"],
        stage="dbt_freshness",
        raise_on_error=False,
    )
    return {
        "test": _result_dict(test),
        "freshness": _result_dict(freshness),
        "freshness_ok": freshness.ok or freshness.skipped,
    }
