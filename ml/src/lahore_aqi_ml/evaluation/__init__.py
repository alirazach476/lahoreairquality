"""Chronological forecast evaluation and baselines (reference for future models).

Do **not** shuffle time series. Train / validation / test cuts are time-ordered.
SARIMA and XGBoost should plug into :func:`evaluate_predictions` /
:class:`PointForecaster` and be compared against the naive baselines.
"""

from lahore_aqi_ml.evaluation.baselines import (
    DEFAULT_SEASONAL_PERIOD,
    NAIVE_LAST_VALUE,
    SEASONAL_NAIVE,
    baseline_name,
    enough_history_for_seasonal,
    naive_last_value_predictions,
    panel_baseline_predictions,
    seasonal_naive_predictions,
)
from lahore_aqi_ml.evaluation.evaluate import (
    evaluate_predictions,
    format_evaluation_table,
    run_baseline_evaluation,
)
from lahore_aqi_ml.evaluation.metrics import (
    DEFAULT_MAPE_EPSILON,
    mae,
    mape,
    rmse,
    score_predictions,
)
from lahore_aqi_ml.evaluation.protocol import PointForecaster
from lahore_aqi_ml.evaluation.split import (
    assign_chronological_split,
    chronological_cut_times,
    split_masks,
)
from lahore_aqi_ml.evaluation.types import (
    ChronologicalSplitSpec,
    EvaluationRow,
    EvaluationTable,
    MetricScores,
)

__all__ = [
    "ChronologicalSplitSpec",
    "DEFAULT_MAPE_EPSILON",
    "DEFAULT_SEASONAL_PERIOD",
    "EvaluationRow",
    "EvaluationTable",
    "MetricScores",
    "NAIVE_LAST_VALUE",
    "PointForecaster",
    "SEASONAL_NAIVE",
    "assign_chronological_split",
    "baseline_name",
    "chronological_cut_times",
    "enough_history_for_seasonal",
    "evaluate_predictions",
    "format_evaluation_table",
    "mae",
    "mape",
    "naive_last_value_predictions",
    "panel_baseline_predictions",
    "rmse",
    "run_baseline_evaluation",
    "score_predictions",
    "seasonal_naive_predictions",
    "split_masks",
]
