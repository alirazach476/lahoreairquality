"""Inference-time features — same pipeline as training (anti-skew).

Always call ``lahore_aqi_ml.features.build_feature_dataset`` so lag / rolling /
weather / calendar definitions cannot drift from the training path.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import pandas as pd

from lahore_aqi_ml.features.columns import DEFAULT_LAGS, DEFAULT_ROLLING_WINDOWS
from lahore_aqi_ml.features.pipeline import (
    FeatureBuildConfig,
    FeatureDataset,
    build_feature_dataset,
)
from lahore_aqi_ml.inference.exceptions import InputValidationError, InsufficientHistoryError


def required_history_hours(
    feature_columns: Sequence[str] | None = None,
    *,
    config: FeatureBuildConfig | None = None,
) -> int:
    """Minimum hourly history needed before/at the forecast origin.

    Derived from lag / rolling suffixes on the **trained** feature list when
    provided; otherwise from the shared ``FeatureBuildConfig`` defaults.
    """
    max_k = 0
    if feature_columns:
        for name in feature_columns:
            lag_m = re.search(r"_lag_(\d+)$", name)
            if lag_m:
                max_k = max(max_k, int(lag_m.group(1)))
            roll_m = re.search(r"_roll_(\d+)_", name)
            if roll_m:
                max_k = max(max_k, int(roll_m.group(1)))
    if max_k == 0:
        cfg = config or FeatureBuildConfig()
        max_k = max(
            max(cfg.lags, default=max(DEFAULT_LAGS)),
            max(cfg.rolling_windows, default=max(DEFAULT_ROLLING_WINDOWS)),
        )
    # Need the origin hour plus ``max_k`` prior hours (e.g. lag_24 → 25 rows).
    return int(max_k) + 1


def build_inference_features(
    observations: pd.DataFrame,
    *,
    config: FeatureBuildConfig | None = None,
) -> FeatureDataset:
    """Build the causal feature matrix with the **same** code as training."""
    return build_feature_dataset(observations, config=config)


def assert_sufficient_history(
    observations: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    group_col: str = "station_id",
    time_col: str = "observed_hour",
    station_ids: Sequence[str] | None = None,
    min_hours: int | None = None,
) -> int:
    """Raise ``InsufficientHistoryError`` when any station lacks history.

    Returns the required hour count that was enforced.
    """
    if group_col not in observations.columns or time_col not in observations.columns:
        raise InputValidationError(f"observations must include {group_col!r} and {time_col!r}")
    need = min_hours if min_hours is not None else required_history_hours(feature_columns)
    work = observations
    if station_ids is not None:
        work = work.loc[work[group_col].isin(list(station_ids))]
        if work.empty:
            raise InsufficientHistoryError(
                f"no rows for requested station_ids={list(station_ids)!r}"
            )

    counts = work.groupby(group_col, sort=False)[time_col].nunique()
    short = counts[counts < need]
    if not short.empty:
        detail = ", ".join(f"{sid}={int(n)}" for sid, n in short.items())
        raise InsufficientHistoryError(
            f"insufficient historical data for features "
            f"(need >={need} unique hours per station; got {detail})"
        )
    return need


def origin_feature_matrix(
    feature_dataset: FeatureDataset,
    feature_columns: Sequence[str],
    *,
    group_col: str = "station_id",
    time_col: str = "observed_hour",
    station_ids: Sequence[str] | None = None,
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Select the latest eligible origin row per station and return model inputs.

    Origin = last ``observed_hour`` (optionally ``<= as_of``). Features are taken
    exactly from ``feature_columns`` (training metadata order).
    """
    frame = feature_dataset.frame
    missing = [c for c in feature_columns if c not in frame.columns]
    if missing:
        raise InputValidationError(
            "built features missing columns required by the trained model: "
            + ", ".join(missing[:20])
            + ("..." if len(missing) > 20 else "")
        )

    work = frame.copy()
    work[time_col] = pd.to_datetime(work[time_col], utc=True)
    if station_ids is not None:
        work = work.loc[work[group_col].isin(list(station_ids))]
    if as_of is not None:
        cutoff = pd.Timestamp(as_of)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
        work = work.loc[work[time_col] <= cutoff]
    if work.empty:
        raise InsufficientHistoryError("no observation rows remain after filters")

    # Latest hour per station
    idx = work.groupby(group_col, sort=False)[time_col].idxmax()
    origins = work.loc[idx].copy()
    origins = origins.sort_values([group_col, time_col], kind="mergesort")

    origins = origins.reset_index(drop=True)
    X = origins.loc[:, list(feature_columns)].copy()
    if X.isna().all(axis=1).any():
        bad = origins.loc[X.isna().all(axis=1), group_col].tolist()
        raise InsufficientHistoryError(
            f"all feature values missing at origin for station_id(s): {bad}"
        )

    keys = origins.loc[:, [group_col, time_col]].reset_index(drop=True)
    return pd.concat([keys, X.reset_index(drop=True)], axis=1)
