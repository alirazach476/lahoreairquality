"""Assertions that feature columns do not peek into the future."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def assert_lag_correctness(
    frame: pd.DataFrame,
    *,
    source_col: str,
    lag: int,
    lag_col: str,
    group_col: str = "station_id",
    time_col: str = "observed_hour",
) -> None:
    """``lag_col`` at row i must equal ``source_col`` at i−lag within the group."""
    ordered = frame.sort_values([group_col, time_col], kind="mergesort")
    for _, group in ordered.groupby(group_col, sort=False):
        src = group[source_col].to_numpy()
        lagged = group[lag_col].to_numpy()
        if len(src) <= lag:
            assert np.all(pd.isna(lagged))
            continue
        # First ``lag`` rows must be NaN
        assert np.all(pd.isna(lagged[:lag])), f"{lag_col}: early rows must be NaN"
        expected = src[:-lag]
        actual = lagged[lag:]
        np.testing.assert_allclose(
            actual.astype(float),
            expected.astype(float),
            equal_nan=True,
            err_msg=f"{lag_col} mismatch vs {source_col}.shift({lag})",
        )


def assert_rolling_uses_only_past_or_present(
    frame: pd.DataFrame,
    *,
    source_col: str,
    window: int,
    roll_col: str,
    stat: str = "mean",
    group_col: str = "station_id",
    time_col: str = "observed_hour",
    include_current: bool = True,
    min_periods: int = 1,
) -> None:
    """Recompute the causal window in pure Python and compare."""
    ordered = frame.sort_values([group_col, time_col], kind="mergesort")
    for _, group in ordered.groupby(group_col, sort=False):
        values = group[source_col].to_list()
        actual = group[roll_col].to_list()
        for i in range(len(values)):
            end = i + 1 if include_current else i
            start = max(0, end - window)
            window_vals = values[start:end]
            if len(window_vals) < min_periods or not window_vals:
                assert pd.isna(actual[i]), f"{roll_col}[{i}] should be NaN"
                continue
            # If any NaN in window, pandas rolling mean is NaN for that point
            if any(
                v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v)
                for v in window_vals
            ):
                # pandas skips NaN in rolling by default? Actually rolling.mean skips NaN
                # with min_periods counting non-NaN. Match pandas: use nanmean when enough non-nan.
                arr = np.asarray(window_vals, dtype=float)
                valid = arr[~np.isnan(arr)]
                if len(valid) < min_periods:
                    assert pd.isna(actual[i])
                    continue
                expected = _stat(valid, stat)
            else:
                expected = _stat(np.asarray(window_vals, dtype=float), stat)

            if pd.isna(actual[i]) and np.isnan(expected):
                continue
            np.testing.assert_allclose(
                float(actual[i]),
                float(expected),
                rtol=1e-9,
                atol=1e-9,
                err_msg=f"{roll_col} at i={i} used future or wrong window",
            )


def assert_feature_columns_have_no_future_shift(
    feature_columns: Sequence[str],
) -> None:
    """Guardrail: feature names must not look like lead/target/future labels."""
    banned = ("lead_", "target_", "future_", "fwd_", "forward_")
    offenders = [c for c in feature_columns if any(b in c.lower() for b in banned)]
    if offenders:
        raise AssertionError(
            "feature columns appear to include future labels: " + ", ".join(offenders)
        )


def _stat(arr: np.ndarray, stat: str) -> float:
    if stat == "mean":
        return float(np.mean(arr))
    if stat == "std":
        if len(arr) < 2:
            return float("nan")
        return float(np.std(arr, ddof=1))
    if stat == "min":
        return float(np.min(arr))
    if stat == "max":
        return float(np.max(arr))
    raise ValueError(stat)
