"""End-to-end baseline evaluation table."""

from __future__ import annotations

import pandas as pd

from lahore_aqi_ml.evaluation import (
    ChronologicalSplitSpec,
    format_evaluation_table,
    run_baseline_evaluation,
)
from lahore_aqi_ml.features import make_synthetic_mart_frame


def test_run_baseline_evaluation_produces_table() -> None:
    frame = make_synthetic_mart_frame(n_hours=120, stations=("S1",), seed=1)
    table = run_baseline_evaluation(
        frame,
        value_col="pm25",
        split_spec=ChronologicalSplitSpec(0.7, 0.15, 0.15),
        horizon=1,
        season=24,
    )
    models = {r.model for r in table.rows}
    assert any(m.startswith("naive_last_value") for m in models)
    assert any(m.startswith("seasonal_naive") for m in models)

    test_rows = [r for r in table.rows if r.split == "test"]
    assert test_rows
    assert all(r.n_obs > 0 for r in test_rows)
    assert all(r.n_obs >= r.n_mape for r in test_rows)

    md = format_evaluation_table(table)
    assert "mae" in md.lower() or "naive_last_value" in md
    frame_out = table.to_dataframe()
    assert set(["model", "split", "mae", "rmse", "mape", "n_obs"]).issubset(frame_out.columns)


def test_seasonal_skipped_when_history_short() -> None:
    hours = pd.date_range("2026-01-01", periods=20, freq="h", tz="UTC")
    frame = pd.DataFrame(
        {
            "station_id": ["A"] * len(hours),
            "observed_hour": hours,
            "pm25": range(len(hours)),
        }
    )
    table = run_baseline_evaluation(frame, value_col="pm25", season=24)
    seasonal = [r for r in table.rows if r.model.startswith("seasonal_naive")]
    assert seasonal
    assert all(r.n_obs == 0 for r in seasonal)
    assert any("skipped" in r.notes for r in seasonal)


def test_no_shuffle_invariant_on_reversed_input() -> None:
    frame = make_synthetic_mart_frame(n_hours=96, stations=("S1",), seed=2)
    forward = run_baseline_evaluation(frame, value_col="pm25", season=24)
    reversed_frame = frame.iloc[::-1].reset_index(drop=True)
    backward = run_baseline_evaluation(reversed_frame, value_col="pm25", season=24)
    # Same models/splits → same n_obs and metrics (deterministic on time)
    fwd = {(r.model, r.split): (r.n_obs, r.mae) for r in forward.rows}
    bwd = {(r.model, r.split): (r.n_obs, r.mae) for r in backward.rows}
    assert fwd.keys() == bwd.keys()
    for key in fwd:
        assert fwd[key][0] == bwd[key][0]
        if fwd[key][0] > 0:
            assert abs(fwd[key][1] - bwd[key][1]) < 1e-9
