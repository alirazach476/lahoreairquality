"""Feature dataset assembly and persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lahore_aqi_ml.features import (
    build_feature_dataset,
    make_synthetic_mart_frame,
    save_feature_dataset,
)
from lahore_aqi_ml.features.pipeline import FeatureBuildConfig, validate_mart_columns


def test_validate_mart_columns_requires_inspected_fields(
    tiny_series_frame: pd.DataFrame,
) -> None:
    validate_mart_columns(tiny_series_frame)
    bad = tiny_series_frame.drop(columns=["pressure_hpa"])
    try:
        validate_mart_columns(bad)
        raised = False
    except KeyError:
        raised = True
    assert raised


def test_duplicate_keys_rejected(tiny_series_frame: pd.DataFrame) -> None:
    dup = pd.concat([tiny_series_frame, tiny_series_frame.iloc[[0]]], ignore_index=True)
    try:
        build_feature_dataset(dup, FeatureBuildConfig(lags=(1,), rolling_windows=(3,)))
        ok = False
    except ValueError as exc:
        ok = "duplicate" in str(exc).lower()
    assert ok


def test_save_feature_dataset_writes_parquet_and_docs(tmp_path: Path) -> None:
    frame = make_synthetic_mart_frame(n_hours=36, stations=("S1",))
    dataset = build_feature_dataset(
        frame, FeatureBuildConfig(lags=(1, 2, 3), rolling_windows=(3, 6))
    )
    paths = save_feature_dataset(dataset, tmp_path, name="demo_features")
    assert paths["parquet"].is_file()
    assert paths["metadata"].is_file()
    assert paths["docs"].is_file()

    loaded = pd.read_parquet(paths["parquet"])
    assert len(loaded) == len(dataset.frame)
    meta = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    assert meta["source_mart"] == "marts.mart_air_quality_features"
    assert "leakage_policy" in meta
    assert set(meta["feature_columns"]) == set(dataset.feature_columns)
    docs = paths["docs"].read_text(encoding="utf-8")
    assert "Leakage policy" in docs
    assert "target_" in docs
