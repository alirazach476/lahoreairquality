"""Causal rolling-window features (backward-looking only)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import pandas as pd

from lahore_aqi_ml.features.columns import DEFAULT_ROLLING_WINDOWS

StatName = Literal["mean", "std", "min", "max"]
DEFAULT_STATS: tuple[StatName, ...] = ("mean", "std", "min", "max")


def add_rolling_features(
    frame: pd.DataFrame,
    columns: Sequence[str],
    *,
    windows: Sequence[int] = DEFAULT_ROLLING_WINDOWS,
    stats: Sequence[StatName] = DEFAULT_STATS,
    group_col: str = "station_id",
    time_col: str = "observed_hour",
    include_current: bool = True,
    min_periods: int | None = None,
    prefix: str = "roll",
) -> pd.DataFrame:
    """Append rolling mean / std / min / max ending at timestamp T.

    Windows are **causal**: at row T the window uses only rows with time ≤ T
    within the same ``group_col`` (and ≤ T−1 if ``include_current`` is False).

    Missing history yields NaN until ``min_periods`` observations exist.
    No forward-fill from the future.
    """
    _validate_windows(windows)
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise KeyError(f"rolling columns not in frame: {missing}")

    out = frame.sort_values([group_col, time_col], kind="mergesort").reset_index(drop=True)
    mp_default = 1 if min_periods is None else min_periods
    new_cols: dict[str, pd.Series] = {}

    for col in columns:
        for window in windows:
            for stat in stats:
                name = f"{col}_{prefix}_{window}_{stat}"
                new_cols[name] = out.groupby(group_col, sort=False)[col].transform(
                    lambda s, w=window, m=mp_default, st=stat, cur=include_current: _rolling_stat(
                        s, window=w, min_periods=m, stat=st, include_current=cur
                    )
                )

    if new_cols:
        out = pd.concat([out, pd.DataFrame(new_cols, index=out.index)], axis=1)
    return out


def _rolling_stat(
    series: pd.Series,
    *,
    window: int,
    min_periods: int,
    stat: StatName,
    include_current: bool,
) -> pd.Series:
    base = series if include_current else series.shift(1)
    roller = base.rolling(window=window, min_periods=min_periods)
    if stat == "mean":
        return roller.mean()
    if stat == "std":
        return roller.std()
    if stat == "min":
        return roller.min()
    if stat == "max":
        return roller.max()
    raise ValueError(f"unsupported rolling stat: {stat}")


def _validate_windows(windows: Sequence[int]) -> None:
    if not windows:
        raise ValueError("windows must be non-empty")
    for w in windows:
        if int(w) < 1:
            raise ValueError(f"window must be >= 1, got {w}")
