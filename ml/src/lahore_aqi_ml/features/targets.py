"""Future targets for supervised training (labels — not model inputs)."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from lahore_aqi_ml.features.columns import DEFAULT_TARGET_LEADS


def add_lead_targets(
    frame: pd.DataFrame,
    columns: Sequence[str],
    *,
    leads: Sequence[int] = DEFAULT_TARGET_LEADS,
    group_col: str = "station_id",
    time_col: str = "observed_hour",
    prefix: str = "target",
) -> pd.DataFrame:
    """Append ``{prefix}_{col}_lead_{h}`` = value of ``col`` at T+h.

    These columns are **labels** for training. They must never be used as
    features. Trailing rows without a future observation are NaN.
    """
    for h in leads:
        if int(h) < 1:
            raise ValueError(f"lead must be >= 1, got {h}")

    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise KeyError(f"target columns not in frame: {missing}")

    out = frame.sort_values([group_col, time_col], kind="mergesort").reset_index(drop=True)
    grouped = out.groupby(group_col, sort=False)

    for col in columns:
        for h in leads:
            out[f"{prefix}_{col}_lead_{h}"] = grouped[col].shift(-h)

    return out
