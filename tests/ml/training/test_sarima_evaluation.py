"""SARIMA fit / evaluation vs naive baseline (small seasonal period for speed)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lahore_aqi_ml.evaluation.types import ChronologicalSplitSpec
from lahore_aqi_ml.training.sarima import (
    SarimaConfig,
    fit_sarima,
    one_step_predictions,
    run_sarima_experiment,
    save_sarima_artifacts,
)


def _hourly_series(n: int = 96, season: int = 12) -> pd.DataFrame:
    """Simple seasonal synthetic panel (one station) for fast SARIMA fits."""
    idx = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    t = np.arange(n, dtype=float)
    y = 50 + 10 * np.sin(2 * np.pi * t / season) + 0.05 * t
    return pd.DataFrame(
        {
            "station_id": ["S1"] * n,
            "observed_hour": idx,
            "pm25": y,
            "pm10": y * 1.2,
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


@pytest.fixture
def small_config() -> SarimaConfig:
    return SarimaConfig(
        order=(1, 0, 0),
        seasonal_order=(1, 0, 0, 12),
        maxiter=50,
        horizon=1,
        target_col="pm25",
        select_from_candidates=False,
    )


def test_fit_and_one_step_predictions_aligned(small_config: SarimaConfig) -> None:
    statsmodels = pytest.importorskip("statsmodels")
    del statsmodels
    frame = _hourly_series(96, season=12)
    # Use first 70 hours as train, last 14 as eval
    y = frame.set_index("observed_hour")["pm25"]
    y_train, y_eval = y.iloc[:70], y.iloc[70:]
    fitted = fit_sarima(y_train, small_config)
    pred = one_step_predictions(fitted, y_train, y_eval)
    assert len(pred) == len(y_eval)
    assert pred.index.equals(y_eval.index)
    assert pred.notna().sum() > 0


def test_run_experiment_compares_to_naive(tmp_path: Path, small_config: SarimaConfig) -> None:
    pytest.importorskip("statsmodels")
    frame = _hourly_series(120, season=12)
    result = run_sarima_experiment(
        frame,
        config=small_config,
        split_spec=ChronologicalSplitSpec(0.7, 0.15, 0.15),
        output_dir=tmp_path,
        run_name="test_sarima",
        log_mlflow=False,
    )
    models = {r.model for r in result.metrics_table.rows}
    assert any("sarima" in m for m in models)
    assert any("naive_last_value" in m for m in models)
    assert result.metadata["comparison_vs_naive_mae"] in {"sarima", "naive", "tie"}
    # Artifacts for visualization / logging
    assert (tmp_path / "test_sarima_predictions.parquet").exists()
    assert (tmp_path / "test_sarima_metadata.json").exists()
    assert (tmp_path / "test_sarima_metrics.md").exists()
    preds = pd.read_parquet(tmp_path / "test_sarima_predictions.parquet")
    assert {"y_true", "y_pred_sarima", "y_pred_naive"}.issubset(preds.columns)
    assert len(preds) == result.metadata["n_test"]


def test_candidate_cap_prevents_huge_search() -> None:
    huge = tuple(((1, 0, 0), (0, 0, 0, 12)) for _ in range(20))
    with pytest.raises(ValueError, match="capped at 12"):
        SarimaConfig(select_from_candidates=True, order_candidates=huge)


def test_save_artifacts_roundtrip(tmp_path: Path, small_config: SarimaConfig) -> None:
    pytest.importorskip("statsmodels")
    frame = _hourly_series(80, season=12)
    result = run_sarima_experiment(
        frame,
        config=small_config,
        split_spec=ChronologicalSplitSpec(0.7, 0.1, 0.2),
    )
    paths = save_sarima_artifacts(result, tmp_path, run_name="roundtrip")
    assert paths["predictions"].exists()
    assert paths["metadata"].exists()
