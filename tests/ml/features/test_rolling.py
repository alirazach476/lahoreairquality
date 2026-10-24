"""Rolling-window correctness (causal, no future)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from lahore_aqi_ml.features.leakage import assert_rolling_uses_only_past_or_present
from lahore_aqi_ml.features.pipeline import FeatureBuildConfig, build_feature_dataset
from lahore_aqi_ml.features.rolling import add_rolling_features


def test_rolling_mean_matches_manual_window(tiny_series_frame: pd.DataFrame) -> None:
    out = add_rolling_features(
        tiny_series_frame,
        ["pm25"],
        windows=(3,),
        stats=("mean",),
        include_current=True,
        min_periods=1,
    )
    a = out[out["station_id"] == "A"].reset_index(drop=True)
    # hour 0: [0] → 0
    assert a.loc[0, "pm25_roll_3_mean"] == 0.0
    # hour 2: [0,1,2] → 1
    assert a.loc[2, "pm25_roll_3_mean"] == 1.0
    # hour 5: [3,4,5] → 4
    assert a.loc[5, "pm25_roll_3_mean"] == 4.0


def test_rolling_min_max_std(tiny_series_frame: pd.DataFrame) -> None:
    out = add_rolling_features(
        tiny_series_frame,
        ["pm25"],
        windows=(3,),
        stats=("min", "max", "std"),
        include_current=True,
        min_periods=1,
    )
    a = out[out["station_id"] == "A"].reset_index(drop=True)
    assert a.loc[4, "pm25_roll_3_min"] == 2.0
    assert a.loc[4, "pm25_roll_3_max"] == 4.0
    expected_std = float(np.std([2.0, 3.0, 4.0], ddof=1))
    np.testing.assert_allclose(a.loc[4, "pm25_roll_3_std"], expected_std)


def test_rolling_exclude_current_is_strictly_past(
    tiny_series_frame: pd.DataFrame,
) -> None:
    out = add_rolling_features(
        tiny_series_frame,
        ["pm25"],
        windows=(2,),
        stats=("mean",),
        include_current=False,
        min_periods=1,
    )
    a = out[out["station_id"] == "A"].reset_index(drop=True)
    assert pd.isna(a.loc[0, "pm25_roll_2_mean"])
    # At hour 2, past-only window is hours 0–1 → mean 0.5 (not including 2)
    assert a.loc[2, "pm25_roll_2_mean"] == 0.5


def test_rolling_leakage_helper(tiny_series_frame: pd.DataFrame) -> None:
    out = add_rolling_features(
        tiny_series_frame,
        ["pm25"],
        windows=(3, 6),
        stats=("mean", "min", "max"),
        include_current=True,
        min_periods=1,
    )
    for w in (3, 6):
        for stat in ("mean", "min", "max"):
            assert_rolling_uses_only_past_or_present(
                out,
                source_col="pm25",
                window=w,
                roll_col=f"pm25_roll_{w}_{stat}",
                stat=stat,
                include_current=True,
                min_periods=1,
            )


def test_pipeline_rolling_columns(mart_frame: pd.DataFrame) -> None:
    ds = build_feature_dataset(
        mart_frame,
        FeatureBuildConfig(lags=(1,), rolling_windows=(3, 6, 12, 24)),
    )
    for w in (3, 6, 12, 24):
        for stat in ("mean", "std", "min", "max"):
            assert f"station_aqi_roll_{w}_{stat}" in ds.feature_columns
