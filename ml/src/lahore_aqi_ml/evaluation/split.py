"""Chronological train / validation / test splits (no shuffling)."""

from __future__ import annotations

import pandas as pd

from lahore_aqi_ml.evaluation.types import ChronologicalSplitSpec, SplitName


def chronological_cut_times(
    timestamps: pd.Series,
    spec: ChronologicalSplitSpec | None = None,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (train_end_exclusive, validation_end_exclusive) on sorted unique times.

    - train:      time < train_end
    - validation: train_end <= time < validation_end
    - test:       time >= validation_end
    """
    cfg = spec or ChronologicalSplitSpec()
    unique = (
        pd.to_datetime(timestamps, utc=True).drop_duplicates().sort_values().reset_index(drop=True)
    )
    n = len(unique)
    if n < 3:
        raise ValueError(f"need at least 3 distinct timestamps for chronological split, got {n}")

    n_train = max(1, int(n * cfg.train_fraction))
    n_val = int(n * cfg.validation_fraction)
    # Ensure every split that has a positive fraction gets at least one timestamp
    # when possible, and test always receives the remainder.
    if cfg.validation_fraction > 0 and n_val < 1 and n - n_train >= 2:
        n_val = 1
    if n_train + n_val >= n:
        # Leave at least one timestamp for test.
        overflow = n_train + n_val - (n - 1)
        if n_val >= overflow:
            n_val -= overflow
        else:
            n_train = max(1, n_train - (overflow - n_val))
            n_val = 0

    train_end = unique.iloc[n_train]
    validation_end = unique.iloc[n_train + n_val] if n_val > 0 else train_end
    return pd.Timestamp(train_end), pd.Timestamp(validation_end)


def assign_chronological_split(
    frame: pd.DataFrame,
    *,
    time_col: str = "observed_hour",
    spec: ChronologicalSplitSpec | None = None,
    split_col: str = "split",
) -> pd.DataFrame:
    """Add a ``split`` column using global chronological cuts (no shuffle)."""
    if time_col not in frame.columns:
        raise KeyError(f"missing time column {time_col!r}")

    out = frame.copy()
    out[time_col] = pd.to_datetime(out[time_col], utc=True)
    train_end, validation_end = chronological_cut_times(out[time_col], spec)

    def _label(ts: pd.Timestamp) -> SplitName:
        if ts < train_end:
            return "train"
        if ts < validation_end:
            return "validation"
        return "test"

    out[split_col] = out[time_col].map(_label)
    return out


def split_masks(
    frame: pd.DataFrame,
    *,
    split_col: str = "split",
) -> dict[SplitName, pd.Series]:
    """Boolean masks for each split name."""
    if split_col not in frame.columns:
        raise KeyError(f"missing split column {split_col!r}")
    return {
        "train": frame[split_col] == "train",
        "validation": frame[split_col] == "validation",
        "test": frame[split_col] == "test",
    }
