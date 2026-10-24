"""MLflow tracking helpers and end-to-end logging for training runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from lahore_aqi_ml.evaluation.types import ChronologicalSplitSpec
from lahore_aqi_ml.features import build_feature_dataset, make_synthetic_mart_frame
from lahore_aqi_ml.tracking.mlflow_run import (
    EXPERIMENT_PREFIX,
    TrainingRunSpec,
    configure_mlflow,
    experiment_name_for,
    log_training_run,
    resolve_tracking_uri,
    run_name_for,
)
from lahore_aqi_ml.training.sarima import SarimaConfig, run_sarima_experiment
from lahore_aqi_ml.training.xgboost_model import (
    XgbConfig,
    XgbHyperParams,
    run_xgboost_experiment,
)


def test_experiment_and_run_naming() -> None:
    assert experiment_name_for("sarima") == f"{EXPERIMENT_PREFIX}/sarima"
    assert experiment_name_for("XGBoost") == f"{EXPERIMENT_PREFIX}/xgboost"
    assert run_name_for("xgboost", "target_pm25_lead_1", 1) == ("xgboost__target_pm25_lead_1__h1")
    assert run_name_for("sarima", "pm25", 1, suffix="demo") == "sarima__pm25__h1__demo"


def test_resolve_tracking_uri_never_hardcodes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    assert resolve_tracking_uri(None) is None
    assert resolve_tracking_uri("") is None
    assert resolve_tracking_uri("http://mlflow.example:5000") == ("http://mlflow.example:5000")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://from-env:5000")
    assert resolve_tracking_uri(None) == "http://from-env:5000"
    # Explicit wins over env
    assert resolve_tracking_uri("http://cli:5000") == "http://cli:5000"


def test_log_training_run_sqlite_store(tmp_path: Path) -> None:
    pytest.importorskip("mlflow")
    tracking = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    model = tmp_path / "model.json"
    preds = tmp_path / "preds.parquet"
    report = tmp_path / "metrics.md"
    importance = tmp_path / "importance.csv"
    model.write_text("{}", encoding="utf-8")
    preds.write_bytes(b"PAR1")
    report.write_text("# report\n", encoding="utf-8")
    importance.write_text("feature,importance_gain\na,1\n", encoding="utf-8")

    run_id = log_training_run(
        TrainingRunSpec(
            model_type="xgboost",
            target="target_pm25_lead_1",
            horizon=1,
            parameters={"max_depth": 3, "learning_rate": 0.1},
            feature_configuration={
                "n_features": 2,
                "include_lags": True,
                "include_weather": True,
                "include_time": True,
            },
            metrics={
                "MAE": 1.5,
                "RMSE": 2.0,
                "MAPE": 0.1,
                "training_duration": 3.25,
            },
            artifact_paths={
                "model": model,
                "predictions": preds,
                "evaluation_report": report,
                "feature_importance": importance,
            },
        ),
        tracking_uri=tracking,
    )
    assert run_id is not None

    import mlflow

    configure_mlflow(tracking)
    exp = mlflow.get_experiment_by_name(f"{EXPERIMENT_PREFIX}/xgboost")
    assert exp is not None
    client = mlflow.tracking.MlflowClient(tracking_uri=tracking)
    run = client.get_run(run_id)
    assert run.data.params["model_type"] == "xgboost"
    assert run.data.params["target"] == "target_pm25_lead_1"
    assert run.data.params["forecast_horizon"] == "1"
    assert "MAE" in run.data.metrics
    assert "RMSE" in run.data.metrics
    assert "MAPE" in run.data.metrics
    assert "training_duration" in run.data.metrics


def test_sarima_experiment_logs_to_mlflow(tmp_path: Path) -> None:
    pytest.importorskip("mlflow")
    pytest.importorskip("statsmodels")
    import numpy as np
    import pandas as pd

    n, season = 96, 12
    idx = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    t = np.arange(n, dtype=float)
    y = 50 + 10 * np.sin(2 * np.pi * t / season)
    frame = pd.DataFrame(
        {
            "station_id": ["S1"] * n,
            "observed_hour": idx,
            "pm25": y,
            "pm10": y,
            "o3": 0.05,
            "no2": 10.0,
            "so2": 2.0,
            "co": 0.4,
            "station_aqi": y * 2,
            "city_aqi": y * 2,
            "temperature_c": 20.0,
            "relative_humidity_pct": 40.0,
            "precipitation_mm": 0.0,
            "wind_speed_ms": 2.0,
            "wind_direction_deg": 90.0,
            "pressure_hpa": 1010.0,
        }
    )
    tracking = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    run_sarima_experiment(
        frame,
        config=SarimaConfig(
            order=(1, 0, 0),
            seasonal_order=(0, 0, 0, 12),
            maxiter=40,
            target_col="pm25",
        ),
        split_spec=ChronologicalSplitSpec(0.7, 0.15, 0.15),
        output_dir=tmp_path / "artifacts",
        run_name="mlflow_sarima",
        log_mlflow=True,
        mlflow_tracking_uri=tracking,
    )
    import mlflow

    configure_mlflow(tracking)
    exp = mlflow.get_experiment_by_name(f"{EXPERIMENT_PREFIX}/sarima")
    assert exp is not None
    assert (tmp_path / "artifacts" / "mlflow_sarima_model.pkl").exists()


def test_xgboost_experiment_logs_to_mlflow(tmp_path: Path) -> None:
    pytest.importorskip("mlflow")
    pytest.importorskip("xgboost")
    mart = make_synthetic_mart_frame(n_hours=120, stations=("S1",), seed=3)
    dataset = build_feature_dataset(mart)
    tracking = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    run_xgboost_experiment(
        dataset.frame,
        config=XgbConfig(
            candidates=(XgbHyperParams(max_depth=3, n_estimators=40),),
            early_stopping_rounds=5,
            include_sarima_comparison=False,
            random_state=0,
        ),
        feature_columns=dataset.feature_columns,
        split_spec=ChronologicalSplitSpec(0.7, 0.15, 0.15),
        output_dir=tmp_path / "artifacts",
        run_name="mlflow_xgb",
        log_mlflow=True,
        mlflow_tracking_uri=tracking,
    )
    import mlflow

    configure_mlflow(tracking)
    exp = mlflow.get_experiment_by_name(f"{EXPERIMENT_PREFIX}/xgboost")
    assert exp is not None


def test_disabled_logging_returns_none(tmp_path: Path) -> None:
    assert (
        log_training_run(
            TrainingRunSpec(
                model_type="sarima",
                target="pm25",
                horizon=1,
                parameters={},
                metrics={"MAE": 1.0},
                artifact_paths={},
            ),
            tracking_uri=str(tmp_path),
            enabled=False,
        )
        is None
    )
