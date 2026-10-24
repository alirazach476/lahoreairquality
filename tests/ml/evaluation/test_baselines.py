"""Naive and seasonal-naive prediction correctness."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lahore_aqi_ml.evaluation.baselines import (
    enough_history_for_seasonal,
    naive_last_value_predictions,
    panel_baseline_predictions,
    seasonal_naive_predictions,
)


def test_naive_last_value_horizon_one() -> None:
    y = pd.Series([10.0, 20.0, 30.0, 40.0])
    pred = naive_last_value_predictions(y, horizon=1)
    assert pd.isna(pred.iloc[0])
    np.testing.assert_allclose(pred.iloc[1:].to_numpy(), [10.0, 20.0, 30.0])


def test_seasonal_naive_period() -> None:
    y = pd.Series(np.arange(30, dtype=float))
    pred = seasonal_naive_predictions(y, season=24)
    assert pred.iloc[:24].isna().all()
    np.testing.assert_allclose(pred.iloc[24:].to_numpy(), y.iloc[:6].to_numpy())


def test_enough_history_gate() -> None:
    assert enough_history_for_seasonal(25, season=24) is True
    assert enough_history_for_seasonal(24, season=24) is False


def test_panel_baseline_respects_groups() -> None:
    rows = []
    for station, base in (("A", 0.0), ("B", 100.0)):
        for h in range(5):
            rows.append(
                {
                    "station_id": station,
                    "observed_hour": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(hours=h),
                    "pm25": base + h,
                }
            )
    frame = pd.DataFrame(rows)
    pred = panel_baseline_predictions(frame, value_col="pm25", method="naive_last_value")
    # First row of each station NaN; second of A is 0, second of B is 100
    a = frame["station_id"] == "A"
    b = frame["station_id"] == "B"
    assert pd.isna(pred[a].iloc[0])
    assert pred[a].iloc[1] == pytest.approx(0.0)
    assert pred[b].iloc[1] == pytest.approx(100.0)
