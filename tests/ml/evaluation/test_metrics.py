"""Metric edge cases, especially MAPE near zero."""

from __future__ import annotations

import math

import numpy as np

from lahore_aqi_ml.evaluation.metrics import mape, score_predictions


def test_mae_rmse_exact() -> None:
    scores = score_predictions([1.0, 2.0, 3.0], [1.0, 2.0, 5.0])
    assert scores.n_obs == 3
    np.testing.assert_allclose(scores.mae, 2.0 / 3.0)
    np.testing.assert_allclose(scores.rmse, math.sqrt(4.0 / 3.0))


def test_mape_skips_near_zero_actuals() -> None:
    y_true = np.array([0.0, 1e-12, 10.0, 20.0])
    y_pred = np.array([1.0, 1.0, 12.0, 20.0])
    value, n_used, n_skipped = mape(y_true, y_pred, epsilon=1e-8)
    assert n_skipped == 2
    assert n_used == 2
    np.testing.assert_allclose(value, (0.2 + 0.0) / 2.0)


def test_mape_none_when_all_near_zero() -> None:
    scores = score_predictions([0.0, 0.0], [1.0, 2.0])
    assert scores.n_obs == 2
    assert scores.mape is None
    assert scores.n_mape == 0
    assert scores.mape_skipped_near_zero == 2


def test_pairwise_drops_nan() -> None:
    scores = score_predictions([1.0, np.nan, 3.0], [1.0, 2.0, 3.0])
    assert scores.n_obs == 2
    np.testing.assert_allclose(scores.mae, 0.0)
