"""SARIMA data preparation — chronological, no shuffle."""

from __future__ import annotations

import pytest

from lahore_aqi_ml.evaluation.types import ChronologicalSplitSpec
from lahore_aqi_ml.features import make_synthetic_mart_frame
from lahore_aqi_ml.training.data import prepare_univariate_series


def test_prepare_selects_station_and_target() -> None:
    frame = make_synthetic_mart_frame(n_hours=80, stations=("S1", "S2"), seed=1)
    prepared = prepare_univariate_series(frame, target_col="pm25", station_id="S2")
    assert prepared.station_id == "S2"
    assert prepared.target_col == "pm25"
    assert prepared.series.index.is_monotonic_increasing
    assert len(prepared.train) > 0 and len(prepared.test) > 0


def test_prepare_rejects_shuffle_requirement_via_time_order() -> None:
    frame = make_synthetic_mart_frame(n_hours=60, stations=("S1",), seed=2)
    reversed_frame = frame.iloc[::-1].reset_index(drop=True)
    prepared = prepare_univariate_series(reversed_frame, target_col="pm25")
    assert prepared.series.index.is_monotonic_increasing
    # Split labels never go backwards in time
    labels = prepared.frame.sort_index()["split"].tolist()
    rank = {"train": 0, "validation": 1, "test": 2}
    assert [rank[x] for x in labels] == sorted(rank[x] for x in labels)


def test_prepare_drops_non_finite_target() -> None:
    frame = make_synthetic_mart_frame(n_hours=40, stations=("S1",), seed=3)
    frame = frame.copy()
    frame.loc[frame.index[5], "pm25"] = float("nan")
    prepared = prepare_univariate_series(frame, target_col="pm25")
    assert prepared.series.isna().sum() == 0


def test_prepare_unknown_station() -> None:
    frame = make_synthetic_mart_frame(n_hours=30, stations=("S1",), seed=4)
    with pytest.raises(ValueError, match="no rows"):
        prepare_univariate_series(frame, station_id="MISSING")


def test_split_fractions_respected() -> None:
    frame = make_synthetic_mart_frame(n_hours=100, stations=("S1",), seed=5)
    prepared = prepare_univariate_series(
        frame,
        split_spec=ChronologicalSplitSpec(0.7, 0.15, 0.15),
    )
    n = len(prepared.series)
    assert len(prepared.train) >= int(0.5 * n)
    assert len(prepared.test) >= 1
