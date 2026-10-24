"""Assets: dbt transformations."""

from dagster import AssetKey, asset

from lahore_aqi_dagster.logging_utils import log_stage
from lahore_aqi_dagster.resources.dbt import DbtResource
from lahore_aqi_dagster.stages.dbt_transform import run_dbt_transform


@asset(
    key=AssetKey(["analytics", "dbt_models"]),
    group_name="analytics",
    deps=[AssetKey(["ingestion", "raw_observations_loaded"])],
    description=(
        "Run dbt seed + dbt run (staging → intermediate → marts). "
        "Transformation failures are not retried automatically."
    ),
)
def dbt_models(
    context,
    dbt: DbtResource,
):
    log_stage(
        context,
        "stage_started",
        stage="dbt_run",
        project=str(dbt._project_dir()),  # noqa: SLF001
        available=dbt.available(),
    )
    result = run_dbt_transform(dbt)
    log_stage(
        context,
        "stage_succeeded",
        stage="dbt_run",
        skipped=result.run.get("skipped"),
    )
    context.add_output_metadata(
        {
            "seed_skipped": result.seed.get("skipped"),
            "run_skipped": result.run.get("skipped"),
            "run_returncode": result.run.get("returncode"),
        }
    )
    return {"seed": result.seed, "run": result.run}
