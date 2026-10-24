"""Weather feature selection / light transforms (same-hour, no lookahead)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from lahore_aqi_ml.features.columns import WEATHER_COLUMNS


def add_weather_features(
    frame: pd.DataFrame,
    columns: Sequence[str] = WEATHER_COLUMNS,
    *,
    add_wind_cyclic: bool = True,
    prefix: str = "wx",
) -> pd.DataFrame:
    """Copy weather columns as ``{prefix}_{col}`` features.

    Values are already aligned to ``observed_hour`` on the mart (same-hour join).
    Optional sin/cos encoding for wind direction (degrees → radians).
    """
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise KeyError(f"weather columns not in frame: {missing}")

    out = frame.copy()
    for col in columns:
        out[f"{prefix}_{col}"] = out[col]

    if add_wind_cyclic and "wind_direction_deg" in columns:
        rad = np.deg2rad(out["wind_direction_deg"].astype("float64"))
        out[f"{prefix}_wind_dir_sin"] = np.sin(rad)
        out[f"{prefix}_wind_dir_cos"] = np.cos(rad)

    return out
