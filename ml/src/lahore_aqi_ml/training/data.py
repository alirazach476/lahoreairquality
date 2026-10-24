"""Chronological univariate series preparation for SARIMA (no shuffling)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from lahore_aqi_ml.evaluation.split import assign_chronological_split
from lahore_aqi_ml.evaluation.types import ChronologicalSplitSpec

# Project default forecast target (mart / feature grain).
DEFAULT_TARGET_COL = "pm25"
DEFAULT_TIME_COL = "observed_hour"
DEFAULT_GROUP_COL = "station_id"


@dataclass(frozen=True, slots=True)
class PreparedSeries:
    """Univariate hourly series for one station with chronological split labels."""

    series: pd.Series
    frame: pd.DataFrame
    station_id: str
    target_col: str
    time_col: str
    train_end: pd.Timestamp
    validation_end: pd.Timestamp

    @property
    def train(self) -> pd.Series:
        return self.series.loc[self.frame["split"] == "train"]

    @property
    def validation(self) -> pd.Series:
        return self.series.loc[self.frame["split"] == "validation"]

    @property
    def test(self) -> pd.Series:
        return self.series.loc[self.frame["split"] == "test"]

    @property
    def train_validation(self) -> pd.Series:
        mask = self.frame["split"].isin(["train", "validation"])
        return self.series.loc[mask]


def prepare_univariate_series(
    frame: pd.DataFrame,
    *,
    target_col: str = DEFAULT_TARGET_COL,
    station_id: str | None = None,
    group_col: str = DEFAULT_GROUP_COL,
    time_col: str = DEFAULT_TIME_COL,
    split_spec: ChronologicalSplitSpec | None = None,
) -> PreparedSeries:
    """Build a sorted, gap-tolerant hourly series for one station.

    - Selects ``station_id`` (default: first station in chronological order of appearance).
    - Sorts by ``time_col`` — **never** shuffles.
    - Drops rows with non-finite target values.
    - Assigns chronological train / validation / test labels.
    """
    if target_col not in frame.columns:
        raise KeyError(f"target column {target_col!r} not in frame")
    if time_col not in frame.columns:
        raise KeyError(f"time column {time_col!r} not in frame")
    if group_col not in frame.columns:
        raise KeyError(f"group column {group_col!r} not in frame")

    work = frame.copy()
    work[time_col] = pd.to_datetime(work[time_col], utc=True)
    work = work.sort_values([group_col, time_col], kind="mergesort")

    if station_id is None:
        station_id = str(work[group_col].iloc[0])
    station_id = str(station_id)

    subset = work.loc[work[group_col].astype(str) == station_id].copy()
    if subset.empty:
        raise ValueError(f"no rows for station_id={station_id!r}")

    subset = subset.dropna(subset=[target_col])
    subset = subset[pd.to_numeric(subset[target_col], errors="coerce").notna()]
    if subset.empty:
        raise ValueError(f"no finite {target_col!r} values for station_id={station_id!r}")

    # Unique timestamp index (keep last if duplicates)
    subset = subset.drop_duplicates(subset=[time_col], keep="last")
    subset = assign_chronological_split(subset, time_col=time_col, spec=split_spec)
    subset = subset.sort_values(time_col, kind="mergesort").reset_index(drop=True)

    index = pd.DatetimeIndex(subset[time_col], name=time_col)
    # Prefer an explicit hourly frequency when the series is regular.
    try:
        inferred = pd.infer_freq(index)
        if inferred is not None:
            index = pd.DatetimeIndex(
                index.values,
                freq=inferred,
                name=time_col,
                tz=getattr(index, "tz", None),
            )
    except (ValueError, TypeError, AttributeError):
        pass
    series = pd.Series(
        subset[target_col].astype("float64").to_numpy(),
        index=index,
        name=target_col,
    )
    # Mirror split labels on a frame aligned to the series index
    aligned = subset[[time_col, "split", target_col]].copy()
    aligned = aligned.set_index(time_col)
    aligned.index = series.index

    train_end = aligned.index[aligned["split"] == "train"]
    val_times = aligned.index[aligned["split"] == "validation"]
    test_times = aligned.index[aligned["split"] == "test"]
    if len(train_end) == 0 or len(test_times) == 0:
        raise ValueError("chronological split produced empty train or test; need more timestamps")

    # Cut markers for metadata (first timestamp of next segment)
    train_end_ts = val_times.min() if len(val_times) else test_times.min()
    validation_end_ts = test_times.min()

    return PreparedSeries(
        series=series,
        frame=aligned,
        station_id=station_id,
        target_col=target_col,
        time_col=time_col,
        train_end=pd.Timestamp(train_end_ts),
        validation_end=pd.Timestamp(validation_end_ts),
    )
