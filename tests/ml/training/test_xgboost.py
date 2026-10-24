"""XGBoost training on causal features — chronological split, no future leakage."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from lahore_aqi_ml.evaluation.types import ChronologicalSplitSpec
from lahore_aqi_ml.features import build_feature_dataset, make_synthetic_mart_frame
from lahore_aqi_ml.training.xgboost_model import (
    DEFAULT_XGB_CANDIDATES,
    XgbConfig,
    XgbHyperParams,
    run_xgboost_experiment,
    select_feature_columns,
)


@pytest.fixture
def feature_frame() -> pd.DataFrame:
    mart = make_synthetic_mart_frame(n_hours=168, stations=("S1",), seed=11)
    return build_feature_dataset(mart).frame


@pytest.fixture
def small_xgb_config() -> XgbConfig:
    return XgbConfig(
        target_col="target_pm25_lead_1",
        value_col="pm25",
        horizon=1,
        early_stopping_rounds=10,
        candidates=(
            XgbHyperParams(max_depth=3, learning_rate=0.1, n_estimators=80),
            XgbHyperParams(max_depth=4, learning_rate=0.08, n_estimators=100),
        ),
        include_sarima_comparison=True,
        sarima_order=(1, 0, 0),
        sarima_seasonal_order=(0, 0, 0, 12),
        random_state=0,
    )


def test_select_feature_columns_excludes_targets(feature_frame: pd.DataFrame) -> None:
    cols = select_feature_columns(feature_frame)
    assert cols
    assert all(not c.startswith("target_") for c in cols)
    assert any("_lag_" in c for c in cols)
    assert any(c.startswith("wx_") for c in cols)
    assert any(c.startswith("feat_") for c in cols)


def test_candidate_cap() -> None:
    huge = tuple(XgbHyperParams() for _ in range(20))
    with pytest.raises(ValueError, match="capped"):
        XgbConfig(candidates=huge)


def test_run_experiment_artifacts_and_baselines(
    tmp_path: Path,
    feature_frame: pd.DataFrame,
    small_xgb_config: XgbConfig,
) -> None:
    pytest.importorskip("xgboost")
    pytest.importorskip("statsmodels")

    dataset = build_feature_dataset(
        make_synthetic_mart_frame(n_hours=168, stations=("S1",), seed=11)
    )
    result = run_xgboost_experiment(
        feature_frame,
        config=small_xgb_config,
        feature_columns=dataset.feature_columns,
        split_spec=ChronologicalSplitSpec(0.7, 0.15, 0.15),
        output_dir=tmp_path,
        run_name="test_xgb",
        log_mlflow=False,
    )

    models = {r.model for r in result.metrics_table.rows}
    assert any(m.startswith("xgboost") for m in models)
    assert any("naive" in m for m in models)
    assert any("seasonal" in m for m in models)
    assert any("sarima" in m for m in models)

    for r in result.metrics_table.rows:
        if r.n_obs > 0:
            assert r.mae == r.mae  # not NaN
            assert r.rmse == r.rmse

    assert (tmp_path / "test_xgb_model.json").exists()
    assert (tmp_path / "test_xgb_predictions.parquet").exists()
    assert (tmp_path / "test_xgb_feature_importance.csv").exists()
    assert (tmp_path / "test_xgb_metadata.json").exists()
    assert (tmp_path / "test_xgb_metrics.csv").exists()
    assert (tmp_path / "test_xgb_metrics.md").exists()

    preds = pd.read_parquet(tmp_path / "test_xgb_predictions.parquet")
    assert {
        "y_true",
        "y_pred_xgboost",
        "y_pred_naive",
        "y_pred_seasonal_naive",
        "y_pred_sarima",
    }.issubset(preds.columns)
    assert len(preds) == result.metadata["n_test"]
    assert result.best_params
    assert result.feature_importance["feature"].tolist()
    assert "lowest_mae_among_measured" in result.metadata


def test_no_target_columns_in_model_features(
    tmp_path: Path,
    feature_frame: pd.DataFrame,
    small_xgb_config: XgbConfig,
) -> None:
    pytest.importorskip("xgboost")
    cfg = XgbConfig(
        target_col=small_xgb_config.target_col,
        value_col=small_xgb_config.value_col,
        horizon=1,
        early_stopping_rounds=5,
        candidates=(DEFAULT_XGB_CANDIDATES[0],),
        include_sarima_comparison=False,
        random_state=0,
    )
    result = run_xgboost_experiment(
        feature_frame,
        config=cfg,
        split_spec=ChronologicalSplitSpec(0.7, 0.15, 0.15),
        output_dir=tmp_path,
        run_name="leak_check",
        log_mlflow=False,
    )
    assert all(not c.startswith("target_") for c in result.feature_columns)
    assert all("lead_" not in c for c in result.feature_columns)
