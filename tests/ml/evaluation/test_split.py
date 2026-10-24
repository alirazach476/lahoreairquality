"""Chronological split must never shuffle time."""

from __future__ import annotations

import pandas as pd
import pytest

from lahore_aqi_ml.evaluation.split import (
    assign_chronological_split,
    chronological_cut_times,
)
from lahore_aqi_ml.evaluation.types import ChronologicalSplitSpec


def _frame(n: int = 100) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "station_id": ["A"] * n,
            "observed_hour": pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
            "pm25": range(n),
        }
    )


def test_fractions_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        ChronologicalSplitSpec(0.5, 0.5, 0.5)


def test_cut_times_are_monotonic() -> None:
    frame = _frame(100)
    train_end, val_end = chronological_cut_times(frame["observed_hour"])
    assert train_end <= val_end
    assert train_end > frame["observed_hour"].min()
    assert val_end < frame["observed_hour"].max() or train_end < frame["observed_hour"].max()


def test_assign_split_is_chronological_not_shuffled() -> None:
    frame = _frame(100)
    # Deliberately reverse input order — split must still follow time.
    shuffled_input = frame.iloc[::-1].reset_index(drop=True)
    out = assign_chronological_split(shuffled_input)
    ordered = out.sort_values("observed_hour")
    labels = ordered["split"].tolist()

    # Once we leave train, we never return to train; same for validation → test.
    def _rank(label: str) -> int:
        return {"train": 0, "validation": 1, "test": 2}[label]

    ranks = [_rank(x) for x in labels]
    assert ranks == sorted(ranks)
    assert "train" in labels and "test" in labels


def test_all_rows_same_timestamp_bucket() -> None:
    """Two stations at the same hours share identical split labels."""
    rows = []
    hours = pd.date_range("2026-01-01", periods=40, freq="h", tz="UTC")
    for station in ("A", "B"):
        for h in hours:
            rows.append({"station_id": station, "observed_hour": h, "pm25": 1.0})
    out = assign_chronological_split(pd.DataFrame(rows))
    pivoted = out.pivot_table(
        index="observed_hour", columns="station_id", values="split", aggfunc="first"
    )
    assert (pivoted["A"] == pivoted["B"]).all()
