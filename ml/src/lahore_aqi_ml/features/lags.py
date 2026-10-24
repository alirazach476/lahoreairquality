"""Causal lag features — values at T-k only (never future)."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from lahore_aqi_ml.features.columns import DEFAULT_LAGS


def add_lag_features(
    frame: pd.DataFrame,
    columns: Sequence[str],
    *,
    lags: Sequence[int] = DEFAULT_LAGS,
    group_col: str = "station_id",
    time_col: str = "observed_hour",
    prefix: str = "lag",
) -> pd.DataFrame:
    """Append ``{col}_{prefix}_{k}`` = value of ``col`` at T−k within each group.

    Requires rows sorted by ``time_col`` within ``group_col``. Uses ``shift(k)``
    so index ``i`` never sees rows after ``i``. Missing history → NaN (not filled).
    """
    _validate_lags(lags)
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise KeyError(f"lag columns not in frame: {missing}")

    out = frame.sort_values([group_col, time_col], kind="mergesort").reset_index(drop=True)
    grouped = out.groupby(group_col, sort=False)
    new_cols: dict[str, pd.Series] = {}

    for col in columns:
        for k in lags:
            new_cols[f"{col}_{prefix}_{k}"] = grouped[col].shift(k)

    if new_cols:
        out = pd.concat([out, pd.DataFrame(new_cols, index=out.index)], axis=1)
    return out


def _validate_lags(lags: Sequence[int]) -> None:
    if not lags:
        raise ValueError("lags must be non-empty")
    for k in lags:
        if int(k) < 1:
            raise ValueError(f"lag must be >= 1, got {k}")
