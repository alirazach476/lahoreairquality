"""Configurable SARIMA forecasting for Lahore AQ targets.

Hourly data uses seasonal period ``s=24`` by default. Parameter search is limited
to a small explicit candidate list — never a blind hundred-model grid.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from lahore_aqi_ml.evaluation.baselines import (
    NAIVE_LAST_VALUE,
    baseline_name,
    naive_last_value_predictions,
)
from lahore_aqi_ml.evaluation.evaluate import evaluate_predictions, format_evaluation_table
from lahore_aqi_ml.evaluation.metrics import DEFAULT_MAPE_EPSILON, score_predictions
from lahore_aqi_ml.evaluation.types import ChronologicalSplitSpec, EvaluationTable
from lahore_aqi_ml.tracking.mlflow_run import (
    TrainingRunSpec,
    log_training_run,
    run_name_for,
)
from lahore_aqi_ml.training.data import (
    DEFAULT_TARGET_COL,
    prepare_univariate_series,
)

logger = logging.getLogger(__name__)

# Hourly diurnal seasonality (project observation grain).
DEFAULT_SEASONAL_PERIOD = 24

# Small, explicit candidates only (not an exhaustive search).
DEFAULT_ORDER_CANDIDATES: tuple[tuple[tuple[int, int, int], tuple[int, int, int, int]], ...] = (
    ((1, 0, 1), (1, 0, 1, DEFAULT_SEASONAL_PERIOD)),
    ((1, 1, 1), (1, 0, 1, DEFAULT_SEASONAL_PERIOD)),
    ((2, 0, 1), (0, 1, 1, DEFAULT_SEASONAL_PERIOD)),
)


@dataclass(frozen=True, slots=True)
class SarimaConfig:
    """Configurable SARIMA orders and fit options."""

    order: tuple[int, int, int] = (1, 0, 1)
    seasonal_order: tuple[int, int, int, int] = (1, 0, 1, DEFAULT_SEASONAL_PERIOD)
    trend: str | None = None
    enforce_stationarity: bool = False
    enforce_invertibility: bool = False
    maxiter: int = 200
    # When True, pick among ``order_candidates`` by validation MAE (small list only).
    select_from_candidates: bool = False
    order_candidates: tuple[tuple[tuple[int, int, int], tuple[int, int, int, int]], ...] = (
        DEFAULT_ORDER_CANDIDATES
    )
    horizon: int = 1
    target_col: str = DEFAULT_TARGET_COL
    mape_epsilon: float = DEFAULT_MAPE_EPSILON

    def __post_init__(self) -> None:
        if self.horizon < 1:
            raise ValueError(f"horizon must be >= 1, got {self.horizon}")
        p, d, q = self.order
        if min(p, d, q) < 0:
            raise ValueError(f"order components must be >= 0, got {self.order}")
        P, D, Q, s = self.seasonal_order
        if min(P, D, Q) < 0 or s < 1:
            raise ValueError(f"invalid seasonal_order {self.seasonal_order}")
        if self.select_from_candidates and len(self.order_candidates) > 12:
            raise ValueError(
                "order_candidates is capped at 12 entries to avoid blind large searches "
                f"(got {len(self.order_candidates)})"
            )


@dataclass
class SarimaFitResult:
    """Fitted SARIMA plus evaluation artifacts."""

    config: SarimaConfig
    station_id: str
    model_name: str
    fitted: Any
    train_aic: float | None
    predictions: pd.DataFrame
    metrics_table: EvaluationTable
    metadata: dict[str, Any] = field(default_factory=dict)


def _require_statsmodels():
    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "statsmodels is required for SARIMA. Install with: pip install 'lahore-aqi-ml[ ]' "
            "or pip install statsmodels"
        ) from exc
    return SARIMAX


def fit_sarima(
    y_train: pd.Series,
    config: SarimaConfig,
) -> Any:
    """Fit a SARIMAX model on chronological training data."""
    SARIMAX = _require_statsmodels()
    if y_train.empty:
        raise ValueError("y_train is empty")
    model = SARIMAX(
        y_train.astype("float64"),
        order=config.order,
        seasonal_order=config.seasonal_order,
        trend=config.trend,
        enforce_stationarity=config.enforce_stationarity,
        enforce_invertibility=config.enforce_invertibility,
    )
    logger.info(
        "sarima_fit_start order=%s seasonal_order=%s n_train=%s",
        config.order,
        config.seasonal_order,
        len(y_train),
    )
    fitted = model.fit(disp=False, maxiter=config.maxiter)
    aic = float(fitted.aic) if fitted.aic is not None else None
    logger.info("sarima_fit_done aic=%s", aic)
    return fitted


def one_step_predictions(
    fitted: Any,
    y_train: pd.Series,
    y_eval: pd.Series,
) -> pd.Series:
    """1-step-ahead predictions on ``y_eval`` without refitting (filter path).

    Uses training estimates with observed history through each evaluation point,
    comparable to the naive last-value baseline at horizon=1.
    """
    if y_eval.empty:
        return pd.Series(dtype="float64", name="sarima_pred")
    extended = pd.concat([y_train, y_eval])
    extended = extended[~extended.index.duplicated(keep="last")].sort_index()
    applied = fitted.apply(extended, refit=False)
    pred = applied.get_prediction(start=y_eval.index[0], end=y_eval.index[-1])
    out = pred.predicted_mean.reindex(y_eval.index)
    out.name = "sarima_pred"
    return out


def multi_step_forecast(
    fitted: Any,
    *,
    steps: int,
) -> pd.Series:
    """Pure multi-step forecast from the end of the training sample."""
    if steps < 1:
        raise ValueError("steps must be >= 1")
    fc = fitted.forecast(steps=steps)
    fc.name = "sarima_forecast"
    return fc


def select_order_on_validation(
    y_train: pd.Series,
    y_validation: pd.Series,
    config: SarimaConfig,
) -> SarimaConfig:
    """Choose among a **small** candidate list by validation MAE (1-step)."""
    if y_validation.empty:
        logger.warning("sarima_select_skip empty_validation using_default_order")
        return config

    best_cfg = config
    best_mae = float("inf")
    for order, seasonal_order in config.order_candidates:
        cand = SarimaConfig(
            order=order,
            seasonal_order=seasonal_order,
            trend=config.trend,
            enforce_stationarity=config.enforce_stationarity,
            enforce_invertibility=config.enforce_invertibility,
            maxiter=config.maxiter,
            select_from_candidates=False,
            horizon=config.horizon,
            target_col=config.target_col,
            mape_epsilon=config.mape_epsilon,
        )
        try:
            fitted = fit_sarima(y_train, cand)
            pred = one_step_predictions(fitted, y_train, y_validation)
            scores = score_predictions(
                y_validation.to_numpy(),
                pred.to_numpy(),
                mape_epsilon=config.mape_epsilon,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sarima_candidate_failed order=%s seasonal=%s error=%s",
                order,
                seasonal_order,
                type(exc).__name__,
            )
            continue
        logger.info(
            "sarima_candidate order=%s seasonal=%s val_mae=%s n=%s",
            order,
            seasonal_order,
            scores.mae,
            scores.n_obs,
        )
        if scores.n_obs > 0 and scores.mae < best_mae:
            best_mae = scores.mae
            best_cfg = cand

    logger.info(
        "sarima_selected order=%s seasonal_order=%s val_mae=%s",
        best_cfg.order,
        best_cfg.seasonal_order,
        best_mae if best_mae < float("inf") else None,
    )
    return best_cfg


def _naive_one_step(y_full: pd.Series, eval_index: pd.DatetimeIndex) -> pd.Series:
    pred = naive_last_value_predictions(y_full, horizon=1)
    return pred.reindex(eval_index)


def run_sarima_experiment(
    frame: pd.DataFrame,
    *,
    config: SarimaConfig | None = None,
    station_id: str | None = None,
    split_spec: ChronologicalSplitSpec | None = None,
    output_dir: str | Path | None = None,
    run_name: str = "sarima",
    log_mlflow: bool = True,
    mlflow_tracking_uri: str | None = None,
) -> SarimaFitResult:
    """Fit SARIMA, score test forecasts, compare to naive baseline, save artifacts."""
    t0 = time.perf_counter()
    cfg = config or SarimaConfig()
    prepared = prepare_univariate_series(
        frame,
        target_col=cfg.target_col,
        station_id=station_id,
        split_spec=split_spec,
    )

    y_train = prepared.train
    y_val = prepared.validation
    y_test = prepared.test

    if cfg.select_from_candidates:
        cfg = select_order_on_validation(y_train, y_val, cfg)

    # Refit on train+validation when validation exists; else train only.
    y_fit = prepared.train_validation if len(y_val) else y_train
    fitted = fit_sarima(y_fit, cfg)
    train_aic = float(fitted.aic) if getattr(fitted, "aic", None) is not None else None

    # Horizon: 1-step filter predictions on test (fair vs naive_h1).
    # Also store a pure multi-step forecast path of length len(test) for viz.
    if cfg.horizon == 1:
        sarima_pred = one_step_predictions(fitted, y_fit, y_test)
        forecast_mode = "one_step_filter"
    else:
        # Multi-step ahead from end of fit sample (not iteratively updated).
        sarima_pred = multi_step_forecast(fitted, steps=len(y_test))
        sarima_pred.index = y_test.index
        forecast_mode = f"multi_step_h{cfg.horizon}_block"

    naive_pred = _naive_one_step(prepared.series, y_test.index)
    naive_model = baseline_name(NAIVE_LAST_VALUE, horizon=1)
    sarima_model = f"sarima_o{cfg.order}_s{cfg.seasonal_order}"

    metrics = EvaluationTable(
        rows=[
            evaluate_predictions(
                prepared.frame.loc[y_test.index],
                y_true=y_test,
                y_pred=sarima_pred,
                model=sarima_model,
                split="test",
                target=cfg.target_col,
                horizon=cfg.horizon,
                notes=forecast_mode,
                mape_epsilon=cfg.mape_epsilon,
            ),
            evaluate_predictions(
                prepared.frame.loc[y_test.index],
                y_true=y_test,
                y_pred=naive_pred,
                model=naive_model,
                split="test",
                target=cfg.target_col,
                horizon=1,
                notes="reference_baseline",
                mape_epsilon=cfg.mape_epsilon,
            ),
        ]
    )

    pred_frame = pd.DataFrame(
        {
            "station_id": prepared.station_id,
            "observed_hour": y_test.index,
            "y_true": y_test.to_numpy(),
            "y_pred_sarima": sarima_pred.to_numpy(),
            "y_pred_naive": naive_pred.to_numpy(),
            "split": "test",
            "target": cfg.target_col,
            "horizon": cfg.horizon,
        }
    )

    sarima_row = metrics.rows[0]
    naive_row = metrics.rows[1]
    better = None
    if sarima_row.n_obs > 0 and naive_row.n_obs > 0:
        if sarima_row.mae < naive_row.mae:
            better = "sarima"
        elif naive_row.mae < sarima_row.mae:
            better = "naive"
        else:
            better = "tie"

    metadata: dict[str, Any] = {
        "created_at_utc": datetime.now(tz=UTC).isoformat(),
        "model": sarima_model,
        "station_id": prepared.station_id,
        "target_col": cfg.target_col,
        "horizon": cfg.horizon,
        "forecast_mode": forecast_mode,
        "order": list(cfg.order),
        "seasonal_order": list(cfg.seasonal_order),
        "trend": cfg.trend,
        "train_aic": train_aic,
        "n_train": int(len(y_train)),
        "n_validation": int(len(y_val)),
        "n_fit": int(len(y_fit)),
        "n_test": int(len(y_test)),
        "train_end": prepared.train_end.isoformat(),
        "validation_end": prepared.validation_end.isoformat(),
        "select_from_candidates": cfg.select_from_candidates,
        "metrics": metrics.to_dicts(),
        "comparison_vs_naive_mae": better,
        "note": (
            "Do not claim SARIMA superiority unless comparison_vs_naive_mae == 'sarima' "
            "on measured metrics."
        ),
        "config": asdict(cfg),
    }

    logger.info(
        "sarima_metrics sarima_mae=%s naive_mae=%s n_obs=%s comparison=%s",
        sarima_row.mae,
        naive_row.mae,
        sarima_row.n_obs,
        better,
    )
    logger.info(
        "sarima_params %s",
        json.dumps(
            {
                "order": cfg.order,
                "seasonal_order": cfg.seasonal_order,
                "aic": train_aic,
            },
            default=str,
        ),
    )

    training_duration_seconds = time.perf_counter() - t0
    metadata["training_duration_seconds"] = training_duration_seconds

    result = SarimaFitResult(
        config=cfg,
        station_id=prepared.station_id,
        model_name=sarima_model,
        fitted=fitted,
        train_aic=train_aic,
        predictions=pred_frame,
        metrics_table=metrics,
        metadata=metadata,
    )

    artifact_dir = Path(output_dir) if output_dir is not None else None
    if artifact_dir is None and log_mlflow:
        artifact_dir = Path("ml/training/artifacts/sarima")
    paths: dict[str, Path] = {}
    if artifact_dir is not None:
        paths = save_sarima_artifacts(result, artifact_dir, run_name=run_name)

    if log_mlflow and paths:
        primary = sarima_row
        mlflow_metrics: dict[str, float] = {
            "MAE": float(primary.mae),
            "RMSE": float(primary.rmse),
            "training_duration": float(training_duration_seconds),
        }
        if primary.mape is not None and primary.mape == primary.mape:
            mlflow_metrics["MAPE"] = float(primary.mape)
        # Baseline comparisons (extra; primary metrics are the SARIMA model)
        if naive_row.n_obs > 0:
            mlflow_metrics["baseline_naive_MAE"] = float(naive_row.mae)

        log_training_run(
            TrainingRunSpec(
                model_type="sarima",
                target=cfg.target_col,
                horizon=cfg.horizon,
                parameters={
                    "order": list(cfg.order),
                    "seasonal_order": list(cfg.seasonal_order),
                    "trend": cfg.trend,
                    "select_from_candidates": cfg.select_from_candidates,
                    "maxiter": cfg.maxiter,
                    "station_id": prepared.station_id,
                    "train_aic": train_aic,
                },
                feature_configuration={
                    "kind": "univariate_series",
                    "n_features": 1,
                    "include_lags": False,
                    "include_weather": False,
                    "include_time": False,
                    "source": "target_history_only",
                    "target_col": cfg.target_col,
                },
                metrics=mlflow_metrics,
                artifact_paths={
                    "model": paths["model"],
                    "predictions": paths["predictions"],
                    "evaluation_report": paths["metrics_md"],
                    "metrics_csv": paths["metrics_csv"],
                },
                tags={"station_id": prepared.station_id},
                run_name=run_name_for(
                    "sarima",
                    cfg.target_col,
                    cfg.horizon,
                    suffix=run_name if run_name != "sarima" else None,
                ),
            ),
            tracking_uri=mlflow_tracking_uri,
            enabled=True,
        )

    return result


def save_sarima_artifacts(
    result: SarimaFitResult,
    output_dir: str | Path,
    *,
    run_name: str = "sarima",
) -> dict[str, Path]:
    """Persist model, predictions, metrics table, and metadata for visualization."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pred_path = out / f"{run_name}_predictions.parquet"
    meta_path = out / f"{run_name}_metadata.json"
    metrics_md = out / f"{run_name}_metrics.md"
    metrics_csv = out / f"{run_name}_metrics.csv"
    model_path = out / f"{run_name}_model.pkl"

    result.predictions.to_parquet(pred_path, index=False)
    meta_path.write_text(
        json.dumps(result.metadata, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    md = format_evaluation_table(result.metrics_table)
    comparison = result.metadata.get("comparison_vs_naive_mae")
    metrics_md.write_text(
        f"# SARIMA evaluation\n\n"
        f"Model: `{result.model_name}`  \n"
        f"Station: `{result.station_id}`  \n"
        f"MAE comparison vs naive: **{comparison}** "
        f"(only claim improvement if this equals `sarima`)\n\n"
        f"{md}\n",
        encoding="utf-8",
    )
    result.metrics_table.to_dataframe().to_csv(metrics_csv, index=False)

    # statsmodels results support .save(); fall back to pickle if needed
    try:
        result.fitted.save(str(model_path))
    except Exception:  # noqa: BLE001
        import pickle

        model_path.write_bytes(pickle.dumps(result.fitted))

    logger.info(
        "sarima_artifacts_saved model=%s predictions=%s metadata=%s metrics=%s",
        model_path,
        pred_path,
        meta_path,
        metrics_md,
    )
    return {
        "model": model_path,
        "predictions": pred_path,
        "metadata": meta_path,
        "metrics_md": metrics_md,
        "metrics_csv": metrics_csv,
    }
