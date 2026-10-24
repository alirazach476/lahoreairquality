"""Persist documented feature datasets for model training."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lahore_aqi_ml.features.columns import SOURCE_MART
from lahore_aqi_ml.features.pipeline import FeatureDataset


def save_feature_dataset(
    dataset: FeatureDataset,
    output_dir: str | Path,
    *,
    name: str = "lahore_aqi_features",
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Write parquet + JSON/Markdown documentation for training.

    Layout::

        {output_dir}/
          {name}.parquet
          {name}.metadata.json
          {name}.FEATURES.md
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    parquet_path = out / f"{name}.parquet"
    meta_path = out / f"{name}.metadata.json"
    docs_path = out / f"{name}.FEATURES.md"

    dataset.frame.to_parquet(parquet_path, index=False)

    meta = _build_metadata(dataset, parquet_path, extra_metadata)
    meta_path.write_text(json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8")
    docs_path.write_text(_render_features_markdown(meta), encoding="utf-8")

    return {"parquet": parquet_path, "metadata": meta_path, "docs": docs_path}


def _build_metadata(
    dataset: FeatureDataset,
    parquet_path: Path,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    frame = dataset.frame
    cfg = dataset.config
    return {
        "name": parquet_path.stem,
        "created_at_utc": datetime.now(tz=UTC).isoformat(),
        "source_mart": SOURCE_MART,
        "grain": ["station_id", "observed_hour"],
        "row_count": int(len(frame)),
        "leakage_policy": (
            "Features at timestamp T use only information available at or before T. "
            "Lags use T-k. Rolling windows are backward-looking. "
            "target_*_lead_* columns are labels for supervised learning and must not "
            "be used as model inputs."
        ),
        "key_columns": dataset.key_columns,
        "feature_columns": dataset.feature_columns,
        "target_columns": dataset.target_columns,
        "lags": list(cfg.lags),
        "rolling_windows": list(cfg.rolling_windows),
        "rolling_stats": list(cfg.rolling_stats),
        "rolling_include_current": cfg.include_current_in_rolling,
        "aq_series_columns": list(cfg.aq_columns),
        "weather_columns": list(cfg.weather_columns),
        "time_range": {
            "min_observed_hour": (frame["observed_hour"].min().isoformat() if len(frame) else None),
            "max_observed_hour": (frame["observed_hour"].max().isoformat() if len(frame) else None),
        },
        "null_counts_features": {c: int(frame[c].isna().sum()) for c in dataset.feature_columns},
        "config": asdict(cfg),
        "extra": extra or {},
    }


def _render_features_markdown(meta: dict[str, Any]) -> str:
    feats = "\n".join(f"- `{c}`" for c in meta["feature_columns"])
    targets = "\n".join(f"- `{c}`" for c in meta["target_columns"])
    return f"""# {meta["name"]} — ML feature dataset

Generated: `{meta["created_at_utc"]}`

## Source

- Warehouse mart: `{meta["source_mart"]}`
- Grain: `{meta["grain"]}`
- Rows: **{meta["row_count"]}**
- Time range: `{meta["time_range"]["min_observed_hour"]}` → `{meta["time_range"]["max_observed_hour"]}`

## Leakage policy

{meta["leakage_policy"]}

## Feature columns ({len(meta["feature_columns"])})

Air quality (same-hour + lags {meta["lags"]} + rolling windows {meta["rolling_windows"]}
× {meta["rolling_stats"]}), weather (same-hour), and calendar (hour, dow, month, weekend).

{feats}

## Target columns (labels only)

{targets}

## Files

- Parquet: `{meta["name"]}.parquet`
- Machine-readable metadata: `{meta["name"]}.metadata.json`
"""
