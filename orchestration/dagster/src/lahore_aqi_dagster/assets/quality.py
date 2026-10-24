"""Assets: dbt data-quality checks."""

from dagster import AssetKey, asset

from lahore_aqi_dagster.logging_utils import log_stage
from lahore_aqi_dagster.resources.dbt import DbtResource
from lahore_aqi_dagster.stages.dbt_transform import run_dbt_tests


@asset(
    key=AssetKey(["analytics", "data_quality_checks"]),
    group_name="analytics",
    deps=[AssetKey(["analytics", "dbt_models"])],
    description=(
        "Run dbt test (hard fail) and dbt source freshness (soft), including "
        "quality-layer rules (valid/suspect/invalid — never deletes rows). "
        "See docs/data-quality.md."
    ),
)
def data_quality_checks(
    context,
    dbt: DbtResource,
):
    log_stage(context, "stage_started", stage="data_quality")
    result = run_dbt_tests(dbt)
    log_stage(
        context,
        "stage_succeeded",
        stage="data_quality",
        freshness_ok=result.get("freshness_ok"),
        test_skipped=result.get("test", {}).get("skipped"),
    )
    context.add_output_metadata(
        {
            "test_returncode": result.get("test", {}).get("returncode"),
            "freshness_returncode": result.get("freshness", {}).get("returncode"),
            "freshness_ok": result.get("freshness_ok"),
        }
    )
    return result
