"""Reusable forecast metrics (MAE, RMSE, MAPE with near-zero protection)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from lahore_aqi_ml.evaluation.types import MetricScores

# Absolute values at or below this threshold are excluded from MAPE
# (division by ~0 is undefined / unstable).
DEFAULT_MAPE_EPSILON = 1e-8


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mape(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    epsilon: float = DEFAULT_MAPE_EPSILON,
) -> tuple[float | None, int, int]:
    """Mean absolute percentage error on rows with |y_true| > epsilon.

    Returns ``(mape_fraction, n_used, n_skipped_near_zero)``.
    MAPE is returned as a **fraction** (0.1 = 10%), or ``None`` if no rows qualify.
    """
    abs_true = np.abs(y_true)
    mask = abs_true > epsilon
    n_used = int(mask.sum())
    n_skipped = int((~mask).sum())
    if n_used == 0:
        return None, 0, n_skipped
    values = np.abs(y_true[mask] - y_pred[mask]) / abs_true[mask]
    return float(np.mean(values)), n_used, n_skipped


def pairwise_complete(
    y_true: Sequence[float] | np.ndarray,
    y_pred: Sequence[float] | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Drop pairs where either side is non-finite."""
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    if yt.shape != yp.shape:
        raise ValueError(f"y_true shape {yt.shape} != y_pred shape {yp.shape}")
    mask = np.isfinite(yt) & np.isfinite(yp)
    return yt[mask], yp[mask]


def score_predictions(
    y_true: Sequence[float] | np.ndarray,
    y_pred: Sequence[float] | np.ndarray,
    *,
    mape_epsilon: float = DEFAULT_MAPE_EPSILON,
) -> MetricScores:
    """Compute MAE / RMSE / MAPE on pairwise-complete observations."""
    yt, yp = pairwise_complete(y_true, y_pred)
    n_obs = int(len(yt))
    if n_obs == 0:
        return MetricScores(
            mae=math.nan,
            rmse=math.nan,
            mape=None,
            n_obs=0,
            n_mape=0,
            mape_skipped_near_zero=0,
        )

    mape_value, n_mape, n_skip = mape(yt, yp, epsilon=mape_epsilon)
    return MetricScores(
        mae=mae(yt, yp),
        rmse=rmse(yt, yp),
        mape=mape_value,
        n_obs=n_obs,
        n_mape=n_mape,
        mape_skipped_near_zero=n_skip,
    )
