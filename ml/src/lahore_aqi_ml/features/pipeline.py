"""End-to-end time-aware feature build from mart-shaped frames."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from lahore_aqi_ml.features.calendar import add_calendar_features
from lahore_aqi_ml.features.columns import (
    AQ_SERIES_COLUMNS,
    DEFAULT_LAGS,
    DEFAULT_ROLLING_WINDOWS,
    DEFAULT_TARGET_LEADS,
    KEY_COLUMNS,
    PASSTHROUGH_COLUMNS,
    REQUIRED_INPUT_COLUMNS,
    WEATHER_COLUMNS,
)
from lahore_aqi_ml.features.lags import add_lag_features
from lahore_aqi_ml.features.leakage import assert_feature_columns_have_no_future_shift
from lahore_aqi_ml.features.rolling import DEFAULT_STATS, StatName, add_rolling_features
from lahore_aqi_ml.features.targets import add_lead_targets
from lahore_aqi_ml.features.weather import add_weather_features


@dataclass(frozen=True)
class FeatureBuildConfig:
    """Configuration for causal feature generation."""

    aq_columns: tuple[str, ...] = AQ_SERIES_COLUMNS
    weather_columns: tuple[str, ...] = WEATHER_COLUMNS
    lags: tuple[int, ...] = DEFAULT_LAGS
    rolling_windows: tuple[int, ...] = DEFAULT_ROLLING_WINDOWS
    rolling_stats: tuple[StatName, ...] = DEFAULT_STATS
    target_columns: tuple[str, ...] = ("station_aqi", "city_aqi", "pm25")
    target_leads: tuple[int, ...] = DEFAULT_TARGET_LEADS
    include_current_in_rolling: bool = True
    rolling_min_periods: int = 1
    add_wind_cyclic: bool = True
    group_col: str = "station_id"
    time_col: str = "observed_hour"


@dataclass
class FeatureDataset:
    """Model-ready frame plus column role metadata (features vs targets)."""

    frame: pd.DataFrame
    feature_columns: list[str]
    target_columns: list[str]
    key_columns: list[str] = field(default_factory=lambda: list(KEY_COLUMNS))
    config: FeatureBuildConfig = field(default_factory=FeatureBuildConfig)

    @property
    def X(self) -> pd.DataFrame:
        return self.frame[self.key_columns + self.feature_columns]

    def y(self, column: str) -> pd.Series:
        if column not in self.target_columns:
            raise KeyError(column)
        return self.frame[column]


def validate_mart_columns(frame: pd.DataFrame) -> None:
    """Ensure the input matches inspected ``mart_air_quality_features`` fields."""
    missing = [c for c in REQUIRED_INPUT_COLUMNS if c not in frame.columns]
    if missing:
        raise KeyError(
            "input frame is missing columns from mart_air_quality_features: " + ", ".join(missing)
        )


def build_feature_dataset(
    frame: pd.DataFrame,
    config: FeatureBuildConfig | None = None,
) -> FeatureDataset:
    """Build lag / rolling / weather / calendar features without future leakage.

    Input must be hourly rows at grain ``(station_id, observed_hour)`` as produced
    by ``marts.mart_air_quality_features``. Rows must be unique on that key.

    A feature at timestamp T uses only information available at or before T.
    Lead columns are training **labels**, never features.
    """
    cfg = config or FeatureBuildConfig()
    validate_mart_columns(frame)

    out = frame.copy()
    out[cfg.time_col] = pd.to_datetime(out[cfg.time_col], utc=True)
    out = out.sort_values([cfg.group_col, cfg.time_col], kind="mergesort").reset_index(drop=True)
    _assert_unique_keys(out, cfg.group_col, cfg.time_col)

    out = add_lag_features(
        out,
        cfg.aq_columns,
        lags=cfg.lags,
        group_col=cfg.group_col,
        time_col=cfg.time_col,
    )
    out = add_rolling_features(
        out,
        cfg.aq_columns,
        windows=cfg.rolling_windows,
        stats=cfg.rolling_stats,
        group_col=cfg.group_col,
        time_col=cfg.time_col,
        include_current=cfg.include_current_in_rolling,
        min_periods=cfg.rolling_min_periods,
    )
    out = add_weather_features(
        out,
        cfg.weather_columns,
        add_wind_cyclic=cfg.add_wind_cyclic,
    )
    out = add_calendar_features(out, time_col=cfg.time_col)
    out = add_lead_targets(
        out,
        cfg.target_columns,
        leads=cfg.target_leads,
        group_col=cfg.group_col,
        time_col=cfg.time_col,
    )

    feature_cols = list_feature_columns(out, cfg)
    target_cols = [c for c in out.columns if c.startswith("target_") and "_lead_" in c]
    assert_feature_columns_have_no_future_shift(feature_cols)

    return FeatureDataset(
        frame=out,
        feature_columns=feature_cols,
        target_columns=target_cols,
        key_columns=[cfg.group_col, cfg.time_col],
        config=cfg,
    )


def list_feature_columns(frame: pd.DataFrame, cfg: FeatureBuildConfig) -> list[str]:
    """Explicit feature set: same-hour AQ/weather + engineered causal columns."""
    cols: list[str] = []

    for col in cfg.aq_columns:
        if col in frame.columns:
            cols.append(col)

    for col in cfg.weather_columns:
        wx = f"wx_{col}"
        if wx in frame.columns:
            cols.append(wx)
        elif col in frame.columns:
            cols.append(col)

    for col in frame.columns:
        if col.startswith("wx_wind_dir_"):
            cols.append(col)
        if col.startswith("feat_"):
            cols.append(col)
        if any(col.startswith(f"{aq}_lag_") for aq in cfg.aq_columns):
            cols.append(col)
        if any(col.startswith(f"{aq}_roll_") for aq in cfg.aq_columns):
            cols.append(col)

    # Stable unique order
    seen: set[str] = set()
    ordered: list[str] = []
    for c in cols:
        if c not in seen and c not in PASSTHROUGH_COLUMNS and c not in KEY_COLUMNS:
            seen.add(c)
            ordered.append(c)
    return ordered


def _assert_unique_keys(frame: pd.DataFrame, group_col: str, time_col: str) -> None:
    dupes = frame.duplicated(subset=[group_col, time_col], keep=False)
    if dupes.any():
        n = int(dupes.sum())
        raise ValueError(
            f"duplicate ({group_col}, {time_col}) rows ({n}); features require unique hourly grain"
        )
