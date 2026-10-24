"""Reusable chronological evaluation for baselines and future models."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from lahore_aqi_ml.evaluation.baselines import (
    DEFAULT_SEASONAL_PERIOD,
    NAIVE_LAST_VALUE,
    SEASONAL_NAIVE,
    baseline_name,
    enough_history_for_seasonal,
    panel_baseline_predictions,
)
from lahore_aqi_ml.evaluation.metrics import DEFAULT_MAPE_EPSILON, score_predictions
from lahore_aqi_ml.evaluation.split import assign_chronological_split
from lahore_aqi_ml.evaluation.types import (
    ChronologicalSplitSpec,
    EvaluationRow,
    EvaluationTable,
    SplitName,
)


def evaluate_predictions(
    frame: pd.DataFrame,
    *,
    y_true: pd.Series,
    y_pred: pd.Series,
    model: str,
    split: SplitName,
    target: str,
    horizon: int,
    notes: str = "",
    mape_epsilon: float = DEFAULT_MAPE_EPSILON,
) -> EvaluationRow:
    """Score one model on an already-filtered split frame."""
    scores = score_predictions(y_true, y_pred, mape_epsilon=mape_epsilon)
    return EvaluationRow(
        model=model,
        split=split,
        target=target,
        horizon=horizon,
        mae=scores.mae,
        rmse=scores.rmse,
        mape=scores.mape,
        n_obs=scores.n_obs,
        n_mape=scores.n_mape,
        mape_skipped_near_zero=scores.mape_skipped_near_zero,
        notes=notes,
    )


def run_baseline_evaluation(
    frame: pd.DataFrame,
    *,
    value_col: str = "pm25",
    group_col: str = "station_id",
    time_col: str = "observed_hour",
    split_spec: ChronologicalSplitSpec | None = None,
    horizon: int = 1,
    season: int = DEFAULT_SEASONAL_PERIOD,
    splits: Sequence[SplitName] = ("train", "validation", "test"),
    include_seasonal: bool = True,
    mape_epsilon: float = DEFAULT_MAPE_EPSILON,
) -> EvaluationTable:
    """Evaluate naive + seasonal-naive baselines with a chronological split.

    - Rows are **not** shuffled; split cuts use sorted unique timestamps.
    - Naive last-value: ``ŷ_t = y_{t-horizon}``.
    - Seasonal naive (when enough history): ``ŷ_t = y_{t-season}``.
    - MAPE skips near-zero actuals (|y| ≤ epsilon); ``n_obs`` vs ``n_mape`` reported.
    """
    if value_col not in frame.columns:
        raise KeyError(f"missing value column {value_col!r}")

    working = assign_chronological_split(
        frame,
        time_col=time_col,
        spec=split_spec,
    )
    working = working.sort_values([group_col, time_col], kind="mergesort").reset_index(drop=True)

    naive_pred = panel_baseline_predictions(
        working,
        value_col=value_col,
        group_col=group_col,
        time_col=time_col,
        method=NAIVE_LAST_VALUE,
        horizon=horizon,
    )
    seasonal_pred: pd.Series | None = None
    seasonal_notes = ""
    n_times = int(working[time_col].nunique())
    if include_seasonal:
        if enough_history_for_seasonal(n_times, season=season):
            seasonal_pred = panel_baseline_predictions(
                working,
                value_col=value_col,
                group_col=group_col,
                time_col=time_col,
                method=SEASONAL_NAIVE,
                season=season,
            )
        else:
            seasonal_notes = (
                f"skipped: need >= {season + 1} distinct timestamps for "
                f"season={season}, have {n_times}"
            )

    table = EvaluationTable()
    y = working[value_col]
    naive_model = baseline_name(NAIVE_LAST_VALUE, horizon=horizon)
    seasonal_model = baseline_name(SEASONAL_NAIVE, season=season)

    for split_name in splits:
        mask = working["split"] == split_name
        if not mask.any():
            table.rows.append(
                EvaluationRow(
                    model=naive_model,
                    split=split_name,
                    target=value_col,
                    horizon=horizon,
                    mae=float("nan"),
                    rmse=float("nan"),
                    mape=None,
                    n_obs=0,
                    n_mape=0,
                    notes="empty split",
                )
            )
            continue

        table.rows.append(
            evaluate_predictions(
                working.loc[mask],
                y_true=y.loc[mask],
                y_pred=naive_pred.loc[mask],
                model=naive_model,
                split=split_name,
                target=value_col,
                horizon=horizon,
                mape_epsilon=mape_epsilon,
            )
        )

        if seasonal_pred is not None:
            table.rows.append(
                evaluate_predictions(
                    working.loc[mask],
                    y_true=y.loc[mask],
                    y_pred=seasonal_pred.loc[mask],
                    model=seasonal_model,
                    split=split_name,
                    target=value_col,
                    horizon=horizon,
                    notes=f"season={season}",
                    mape_epsilon=mape_epsilon,
                )
            )
        elif include_seasonal and seasonal_notes:
            table.rows.append(
                EvaluationRow(
                    model=seasonal_model,
                    split=split_name,
                    target=value_col,
                    horizon=horizon,
                    mae=float("nan"),
                    rmse=float("nan"),
                    mape=None,
                    n_obs=0,
                    n_mape=0,
                    notes=seasonal_notes,
                )
            )

    return table


def format_evaluation_table(
    table: EvaluationTable,
    *,
    float_digits: int = 4,
) -> str:
    """Human-readable markdown evaluation table."""
    return table.to_markdown(float_digits=float_digits)
