"""No future information may enter feature columns."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lahore_aqi_ml.features.leakage import assert_feature_columns_have_no_future_shift
from lahore_aqi_ml.features.pipeline import FeatureBuildConfig, build_feature_dataset
from lahore_aqi_ml.features.targets import add_lead_targets


def test_feature_list_excludes_targets(mart_frame: pd.DataFrame) -> None:
    ds = build_feature_dataset(mart_frame)
    assert_feature_columns_have_no_future_shift(ds.feature_columns)
    assert all(not c.startswith("target_") for c in ds.feature_columns)
    assert any(c.startswith("target_") for c in ds.target_columns)


def test_lag_never_equals_future_value(tiny_series_frame: pd.DataFrame) -> None:
    ds = build_feature_dataset(
        tiny_series_frame,
        FeatureBuildConfig(lags=(1,), rolling_windows=(3,), target_leads=(1,)),
    )
    a = ds.frame[ds.frame["station_id"] == "A"].reset_index(drop=True)
    # lag_1 at i is pm25[i-1], never pm25[i+1]
    for i in range(1, len(a) - 1):
        assert a.loc[i, "pm25_lag_1"] == a.loc[i - 1, "pm25"]
        assert (
            a.loc[i, "pm25_lag_1"] != a.loc[i + 1, "pm25"]
            or a.loc[i - 1, "pm25"] == a.loc[i + 1, "pm25"]
        )


def test_rolling_mean_insensitive_to_future_mutation(
    tiny_series_frame: pd.DataFrame,
) -> None:
    """Changing a future row must not change features at earlier timestamps."""
    base = tiny_series_frame.copy()
    ds1 = build_feature_dataset(
        base, FeatureBuildConfig(lags=(1, 2), rolling_windows=(3,), target_leads=(1,))
    )
    mutated = base.copy()
    # Inflate the last hour of station A only
    mask = (mutated["station_id"] == "A") & (
        mutated["observed_hour"] == mutated.loc[mutated["station_id"] == "A", "observed_hour"].max()
    )
    mutated.loc[mask, "pm25"] = 9999.0
    ds2 = build_feature_dataset(
        mutated, FeatureBuildConfig(lags=(1, 2), rolling_windows=(3,), target_leads=(1,))
    )

    a1 = ds1.frame[ds1.frame["station_id"] == "A"].reset_index(drop=True)
    a2 = ds2.frame[ds2.frame["station_id"] == "A"].reset_index(drop=True)
    # All rows except the last must keep identical causal features
    feat = [c for c in ds1.feature_columns if c.startswith("pm25_")]
    for col in feat:
        np.testing.assert_allclose(
            a1.loc[:8, col].astype(float),
            a2.loc[:8, col].astype(float),
            equal_nan=True,
            err_msg=f"future mutation leaked into {col}",
        )


def test_banned_feature_names_raise() -> None:
    with pytest.raises(AssertionError, match="future"):
        assert_feature_columns_have_no_future_shift(["pm25_lag_1", "target_pm25_lead_1"])


def test_lead_targets_are_shifted_forward(tiny_series_frame: pd.DataFrame) -> None:
    out = add_lead_targets(tiny_series_frame, ["pm25"], leads=(1,))
    a = out[out["station_id"] == "A"].reset_index(drop=True)
    assert a.loc[0, "target_pm25_lead_1"] == 1.0
    assert pd.isna(a.loc[9, "target_pm25_lead_1"])
