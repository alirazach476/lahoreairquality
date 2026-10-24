"""Inference layer: model load, feature parity, schema, insufficient history."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from lahore_aqi_ml.evaluation.types import ChronologicalSplitSpec
from lahore_aqi_ml.features import build_feature_dataset, make_synthetic_mart_frame
from lahore_aqi_ml.inference import (
    FORECAST_COLUMNS,
    InputValidationError,
    InsufficientHistoryError,
    ModelNotFoundError,
    forecast,
    load_model_bundle,
    required_history_hours,
)
from lahore_aqi_ml.inference.features import build_inference_features
from lahore_aqi_ml.training.xgboost_model import (
    XgbConfig,
    XgbHyperParams,
    run_xgboost_experiment,
)


@pytest.fixture
def trained_artifact_dir(tmp_path: Path) -> Path:
    pytest.importorskip("xgboost")
    mart = make_synthetic_mart_frame(n_hours=120, stations=("S1",), seed=21)
    dataset = build_feature_dataset(mart)
    out = tmp_path / "xgboost"
    run_xgboost_experiment(
        dataset.frame,
        config=XgbConfig(
            candidates=(XgbHyperParams(max_depth=3, n_estimators=40, learning_rate=0.1),),
            early_stopping_rounds=5,
            include_sarima_comparison=False,
            random_state=0,
        ),
        feature_columns=dataset.feature_columns,
        split_spec=ChronologicalSplitSpec(0.7, 0.15, 0.15),
        output_dir=out,
        run_name="infer_demo",
        log_mlflow=False,
    )
    assert (out / "infer_demo_model.json").exists()
    assert (out / "infer_demo_metadata.json").exists()
    return out


def test_model_loading(trained_artifact_dir: Path) -> None:
    bundle = load_model_bundle(artifact_dir=trained_artifact_dir, run_name="infer_demo")
    assert bundle.model_type == "xgboost"
    assert bundle.horizon >= 1
    assert bundle.feature_columns
    assert bundle.model_version
    assert bundle.model_path.exists()
    assert "target" in bundle.target_col or bundle.target_col


def test_model_not_found(tmp_path: Path) -> None:
    with pytest.raises(ModelNotFoundError):
        load_model_bundle(artifact_dir=tmp_path)


def test_feature_consistency_with_training_pipeline(
    trained_artifact_dir: Path,
) -> None:
    """Inference features must match ``build_feature_dataset`` on the same rows."""
    bundle = load_model_bundle(artifact_dir=trained_artifact_dir, run_name="infer_demo")
    mart = make_synthetic_mart_frame(n_hours=80, stations=("S1",), seed=21)
    train_style = build_feature_dataset(mart)
    infer_style = build_inference_features(mart)

    assert train_style.feature_columns == infer_style.feature_columns
    # Same values for model feature columns at the latest origin
    t = train_style.frame.sort_values("observed_hour").iloc[-1]
    i = infer_style.frame.sort_values("observed_hour").iloc[-1]
    for col in bundle.feature_columns:
        tv, iv = t[col], i[col]
        if pd.isna(tv) and pd.isna(iv):
            continue
        assert tv == pytest.approx(iv) or (pd.isna(tv) and pd.isna(iv))


def test_forecast_output_schema(trained_artifact_dir: Path) -> None:
    bundle = load_model_bundle(artifact_dir=trained_artifact_dir, run_name="infer_demo")
    mart = make_synthetic_mart_frame(n_hours=80, stations=("S1",), seed=21)
    result = forecast(mart, model=bundle)

    assert list(result.forecasts.columns) == list(FORECAST_COLUMNS)
    assert len(result.forecasts) == 1
    row = result.forecasts.iloc[0]
    assert row["station_id"] == "S1"
    assert row["horizon"] == bundle.horizon
    assert row["model_version"] == result.model_version == bundle.model_version
    assert row["model_type"] == "xgboost"
    assert row["target"] == bundle.target_col
    assert pd.notna(row["y_pred"])
    origin = pd.Timestamp(row["origin_hour"])
    forecast_h = pd.Timestamp(row["forecast_hour"])
    assert forecast_h == origin + pd.Timedelta(hours=bundle.horizon)
    assert result.metadata.get("model_path")
    payload = result.as_dict()
    assert payload["n_forecasts"] == 1
    assert "forecasts" in payload


def test_insufficient_history_fails_clearly(trained_artifact_dir: Path) -> None:
    bundle = load_model_bundle(artifact_dir=trained_artifact_dir, run_name="infer_demo")
    need = required_history_hours(bundle.feature_columns)
    short = make_synthetic_mart_frame(n_hours=max(need - 5, 3), stations=("S1",), seed=7)
    with pytest.raises(InsufficientHistoryError, match="insufficient historical data"):
        forecast(short, model=bundle)


def test_empty_and_invalid_inputs(trained_artifact_dir: Path) -> None:
    bundle = load_model_bundle(artifact_dir=trained_artifact_dir, run_name="infer_demo")
    with pytest.raises(InputValidationError, match="empty"):
        forecast(pd.DataFrame(), model=bundle)
    with pytest.raises(InputValidationError):
        forecast(
            pd.DataFrame({"station_id": ["S1"], "observed_hour": ["2026-01-01"]}), model=bundle
        )


def test_required_history_from_metadata_lags() -> None:
    cols = ["pm25_lag_1", "pm25_lag_24", "pm25_roll_12_mean", "wx_temperature_c"]
    assert required_history_hours(cols) == 25


def test_metadata_lists_feature_columns(trained_artifact_dir: Path) -> None:
    meta = json.loads(
        (trained_artifact_dir / "infer_demo_metadata.json").read_text(encoding="utf-8")
    )
    bundle = load_model_bundle(artifact_dir=trained_artifact_dir, run_name="infer_demo")
    assert list(bundle.feature_columns) == list(meta["feature_columns"])
