"""Lag feature correctness and missing-history behavior."""

from __future__ import annotations

import pandas as pd

from lahore_aqi_ml.features.lags import add_lag_features
from lahore_aqi_ml.features.leakage import assert_lag_correctness
from lahore_aqi_ml.features.pipeline import FeatureBuildConfig, build_feature_dataset


def test_lag_values_match_shift(tiny_series_frame: pd.DataFrame) -> None:
    out = add_lag_features(tiny_series_frame, ["pm25"], lags=(1, 2, 3))
    a = out[out["station_id"] == "A"].reset_index(drop=True)
    assert pd.isna(a.loc[0, "pm25_lag_1"])
    assert a.loc[1, "pm25_lag_1"] == 0.0
    assert a.loc[3, "pm25_lag_3"] == 0.0
    assert a.loc[5, "pm25_lag_2"] == 3.0


def test_lag_missing_history_is_nan_not_future_filled(
    tiny_series_frame: pd.DataFrame,
) -> None:
    out = add_lag_features(tiny_series_frame, ["pm25"], lags=(24,))
    # Only 10 rows per station — lag 24 must be entirely NaN
    assert out["pm25_lag_24"].isna().all()


def test_lag_does_not_cross_stations(tiny_series_frame: pd.DataFrame) -> None:
    out = add_lag_features(tiny_series_frame, ["pm25"], lags=(1,))
    b = out[out["station_id"] == "B"].reset_index(drop=True)
    # B starts at 100; lag_1 at hour 0 is NaN (not A's last value)
    assert pd.isna(b.loc[0, "pm25_lag_1"])
    assert b.loc[1, "pm25_lag_1"] == 100.0


def test_assert_lag_correctness_helper(tiny_series_frame: pd.DataFrame) -> None:
    out = add_lag_features(tiny_series_frame, ["station_aqi"], lags=(1, 6))
    assert_lag_correctness(out, source_col="station_aqi", lag=1, lag_col="station_aqi_lag_1")
    assert_lag_correctness(out, source_col="station_aqi", lag=6, lag_col="station_aqi_lag_6")


def test_pipeline_lags_present(mart_frame: pd.DataFrame) -> None:
    ds = build_feature_dataset(
        mart_frame,
        FeatureBuildConfig(lags=(1, 2, 3, 6, 12, 24), rolling_windows=(3,)),
    )
    for k in (1, 2, 3, 6, 12, 24):
        assert f"pm25_lag_{k}" in ds.feature_columns
    # Early rows NaN for lag 24
    first = ds.frame.sort_values(["station_id", "observed_hour"]).groupby("station_id").head(24)
    assert first["pm25_lag_24"].isna().all()
