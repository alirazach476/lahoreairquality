"""Forecasting baselines: last-value (naive) and seasonal naive.

These are the reference models for later SARIMA / XGBoost comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DEFAULT_SEASONAL_PERIOD = 24  # hourly diurnal seasonality


@dataclass(frozen=True, slots=True)
class BaselineSpec:
    """Identity for a baseline method (reusable in evaluation tables)."""

    name: str
    kind: str  # "naive" | "seasonal_naive"
    horizon: int = 1
    season: int | None = None


NAIVE_LAST_VALUE = "naive_last_value"
SEASONAL_NAIVE = "seasonal_naive"


def naive_last_value_predictions(
    series: pd.Series,
    *,
    horizon: int = 1,
) -> pd.Series:
    """Persistence: forecast for time t is the value at t−horizon.

    For horizon=1 this is the classic last-value / random-walk naive forecast.
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    return series.shift(horizon)


def seasonal_naive_predictions(
    series: pd.Series,
    *,
    season: int = DEFAULT_SEASONAL_PERIOD,
) -> pd.Series:
    """Seasonal naive: forecast for time t is the value at t−season."""
    if season < 1:
        raise ValueError(f"season must be >= 1, got {season}")
    return series.shift(season)


def enough_history_for_seasonal(
    n_timestamps: int,
    *,
    season: int,
    min_predictions: int = 1,
) -> bool:
    """True when a series can yield at least ``min_predictions`` seasonal forecasts."""
    return n_timestamps >= season + min_predictions


def panel_baseline_predictions(
    frame: pd.DataFrame,
    *,
    value_col: str,
    group_col: str = "station_id",
    time_col: str = "observed_hour",
    method: str = NAIVE_LAST_VALUE,
    horizon: int = 1,
    season: int = DEFAULT_SEASONAL_PERIOD,
) -> pd.Series:
    """Compute baseline predictions aligned to ``frame`` index (panel-aware).

    Rows are sorted by ``(group_col, time_col)`` within each group for shifting.
    Returned series uses the original index order of ``frame``.
    """
    if value_col not in frame.columns:
        raise KeyError(f"missing value column {value_col!r}")
    if method not in {NAIVE_LAST_VALUE, SEASONAL_NAIVE}:
        raise ValueError(f"unknown baseline method {method!r}")

    work = frame[[group_col, time_col, value_col]].copy()
    work["_orig_pos"] = np.arange(len(work))
    work = work.sort_values([group_col, time_col], kind="mergesort")

    parts: list[pd.Series] = []
    for _, group in work.groupby(group_col, sort=False):
        y = group[value_col]
        if method == NAIVE_LAST_VALUE:
            pred = naive_last_value_predictions(y, horizon=horizon)
        else:
            pred = seasonal_naive_predictions(y, season=season)
        pred.index = group["_orig_pos"]
        parts.append(pred)

    combined = pd.concat(parts).sort_index()
    combined.index = frame.index
    combined.name = f"pred_{method}"
    return combined


def baseline_name(method: str, *, horizon: int = 1, season: int | None = None) -> str:
    if method == NAIVE_LAST_VALUE:
        return f"{NAIVE_LAST_VALUE}_h{horizon}"
    if method == SEASONAL_NAIVE:
        s = season if season is not None else DEFAULT_SEASONAL_PERIOD
        return f"{SEASONAL_NAIVE}_s{s}"
    raise ValueError(method)
