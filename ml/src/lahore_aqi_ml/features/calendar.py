"""Calendar / time features derived from ``observed_hour`` (UTC)."""

from __future__ import annotations

import pandas as pd


def add_calendar_features(
    frame: pd.DataFrame,
    *,
    time_col: str = "observed_hour",
) -> pd.DataFrame:
    """Add hour, day-of-week, month, and weekend indicator (no lookahead).

    All fields are deterministic functions of ``observed_hour`` at row T.
    """
    if time_col not in frame.columns:
        raise KeyError(f"missing time column {time_col!r}")

    out = frame.copy()
    ts = pd.to_datetime(out[time_col], utc=True)
    out["feat_hour"] = ts.dt.hour.astype("int16")
    out["feat_day_of_week"] = ts.dt.dayofweek.astype("int16")  # Mon=0 … Sun=6
    out["feat_month"] = ts.dt.month.astype("int16")
    out["feat_is_weekend"] = (ts.dt.dayofweek >= 5).astype("int8")
    return out
