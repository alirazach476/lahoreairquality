"""Missing-data behavior and calendar / weather features."""

from __future__ import annotations

import numpy as np
import pandas as pd

from lahore_aqi_ml.features.calendar import add_calendar_features
from lahore_aqi_ml.features.lags import add_lag_features
from lahore_aqi_ml.features.pipeline import FeatureBuildConfig, build_feature_dataset
from lahore_aqi_ml.features.rolling import add_rolling_features
from lahore_aqi_ml.features.weather import add_weather_features


def test_internal_nan_propagates_to_lag_without_future_fill(
    tiny_series_frame: pd.DataFrame,
) -> None:
    frame = tiny_series_frame.copy()
    # Punch a hole at hour 4 for station A
    mask = (frame["station_id"] == "A") & (
        frame["observed_hour"] == pd.Timestamp("2026-01-01 04:00", tz="UTC")
    )
    frame.loc[mask, "pm25"] = np.nan
    out = add_lag_features(frame, ["pm25"], lags=(1,))
    a = out[out["station_id"] == "A"].reset_index(drop=True)
    assert pd.isna(a.loc[4, "pm25"])
    assert pd.isna(a.loc[5, "pm25_lag_1"])  # lag sees the hole, not hour 6
    assert a.loc[6, "pm25_lag_1"] == 5.0


def test_rolling_min_periods_leaves_nan_when_insufficient(
    tiny_series_frame: pd.DataFrame,
) -> None:
    out = add_rolling_features(
        tiny_series_frame,
        ["pm25"],
        windows=(5,),
        stats=("mean",),
        include_current=True,
        min_periods=5,
    )
    a = out[out["station_id"] == "A"].reset_index(drop=True)
    assert a.loc[:3, "pm25_roll_5_mean"].isna().all()
    assert not pd.isna(a.loc[4, "pm25_roll_5_mean"])


def test_calendar_features_from_observed_hour(tiny_series_frame: pd.DataFrame) -> None:
    out = add_calendar_features(tiny_series_frame)
    a = out[out["station_id"] == "A"].reset_index(drop=True)
    # 2026-01-01 was Thursday → dayofweek 3; weekend False
    assert a.loc[0, "feat_hour"] == 0
    assert a.loc[0, "feat_day_of_week"] == 3
    assert a.loc[0, "feat_month"] == 1
    assert a.loc[0, "feat_is_weekend"] == 0


def test_weather_features_and_wind_cyclic(tiny_series_frame: pd.DataFrame) -> None:
    out = add_weather_features(tiny_series_frame, add_wind_cyclic=True)
    assert "wx_temperature_c" in out.columns
    assert "wx_relative_humidity_pct" in out.columns
    assert "wx_wind_speed_ms" in out.columns
    assert "wx_wind_direction_deg" in out.columns
    assert "wx_pressure_hpa" in out.columns
    assert "wx_precipitation_mm" in out.columns
    # 90° → sin=1, cos≈0
    np.testing.assert_allclose(out["wx_wind_dir_sin"].iloc[0], 1.0, atol=1e-9)
    np.testing.assert_allclose(out["wx_wind_dir_cos"].iloc[0], 0.0, atol=1e-9)


def test_pipeline_includes_weather_and_time(mart_frame: pd.DataFrame) -> None:
    ds = build_feature_dataset(mart_frame, FeatureBuildConfig(lags=(1,), rolling_windows=(3,)))
    for col in (
        "wx_temperature_c",
        "wx_relative_humidity_pct",
        "wx_wind_speed_ms",
        "wx_wind_direction_deg",
        "wx_pressure_hpa",
        "wx_precipitation_mm",
        "feat_hour",
        "feat_day_of_week",
        "feat_month",
        "feat_is_weekend",
    ):
        assert col in ds.feature_columns
