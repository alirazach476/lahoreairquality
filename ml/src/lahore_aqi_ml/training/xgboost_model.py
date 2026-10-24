"""XGBoost forecasting on the causal feature dataset (no future leakage)."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lahore_aqi_ml.evaluation.baselines import (
    DEFAULT_SEASONAL_PERIOD,
    NAIVE_LAST_VALUE,
    SEASONAL_NAIVE,
    baseline_name,
    enough_history_for_seasonal,
)
from lahore_aqi_ml.evaluation.evaluate import evaluate_predictions, format_evaluation_table
from lahore_aqi_ml.evaluation.metrics import DEFAULT_MAPE_EPSILON, score_predictions
from lahore_aqi_ml.evaluation.split import assign_chronological_split
from lahore_aqi_ml.evaluation.types import ChronologicalSplitSpec, EvaluationTable
from lahore_aqi_ml.tracking.mlflow_run import (
    TrainingRunSpec,
    log_training_run,
    run_name_for,
)
from lahore_aqi_ml.training.sarima import SarimaConfig, fit_sarima, one_step_predictions

logger = logging.getLogger(__name__)

DEFAULT_TARGET = "target_pm25_lead_1"
DEFAULT_VALUE_COL = "pm25"  # series used for naive / seasonal / SARIMA alignment


@dataclass(frozen=True, slots=True)
class XgbHyperParams:
    """One XGBoost hyperparameter setting (small search space)."""

    max_depth: int = 4
    learning_rate: float = 0.08
    n_estimators: int = 300
    min_child_weight: float = 2.0
    subsample: float = 0.9
    colsample_bytree: float = 0.9
    reg_lambda: float = 1.0


# Reasonable, explicit candidates only — not a large random search.
DEFAULT_XGB_CANDIDATES: tuple[XgbHyperParams, ...] = (
    XgbHyperParams(max_depth=3, learning_rate=0.1, n_estimators=200),
    XgbHyperParams(max_depth=4, learning_rate=0.08, n_estimators=300),
    XgbHyperParams(max_depth=5, learning_rate=0.05, n_estimators=400, min_child_weight=3.0),
    XgbHyperParams(
        max_depth=4,
        learning_rate=0.05,
        n_estimators=400,
        subsample=0.8,
        colsample_bytree=0.8,
    ),
)


@dataclass(frozen=True, slots=True)
class XgbConfig:
    """Configurable XGBoost training options."""

    target_col: str = DEFAULT_TARGET
    value_col: str = DEFAULT_VALUE_COL
    horizon: int = 1
    early_stopping_rounds: int = 30
    candidates: tuple[XgbHyperParams, ...] = DEFAULT_XGB_CANDIDATES
    random_state: int = 42
    n_jobs: int = 2
    mape_epsilon: float = DEFAULT_MAPE_EPSILON
    seasonal_period: int = DEFAULT_SEASONAL_PERIOD
    include_sarima_comparison: bool = True
    sarima_order: tuple[int, int, int] = (1, 0, 1)
    sarima_seasonal_order: tuple[int, int, int, int] = (1, 0, 1, 24)

    def __post_init__(self) -> None:
        if self.horizon < 1:
            raise ValueError(f"horizon must be >= 1, got {self.horizon}")
        if len(self.candidates) > 12:
            raise ValueError(
                f"candidates capped at 12 to keep tuning bounded (got {len(self.candidates)})"
            )
        if self.early_stopping_rounds < 1:
            raise ValueError("early_stopping_rounds must be >= 1")


@dataclass
class XgbFitResult:
    model: Any
    model_name: str
    config: XgbConfig
    best_params: dict[str, Any]
    feature_columns: list[str]
    feature_importance: pd.DataFrame
    predictions: pd.DataFrame
    metrics_table: EvaluationTable
    metadata: dict[str, Any] = field(default_factory=dict)
    best_iteration: int | None = None


def _require_xgboost():
    try:
        import xgboost as xgb
    except ImportError as exc:  # pragma: no cover
        raise ImportError("xgboost is required. Install with: pip install xgboost") from exc
    return xgb


def select_feature_columns(
    frame: pd.DataFrame,
    *,
    feature_columns: Sequence[str] | None = None,
) -> list[str]:
    """Prefer lagged AQ/PM, weather, and calendar features; never use targets."""
    if feature_columns is not None:
        cols = [c for c in feature_columns if c in frame.columns]
    else:
        cols = []
        for c in frame.columns:
            if c.startswith("target_"):
                continue
            if "_lag_" in c or "_roll_" in c or c.startswith("wx_") or c.startswith("feat_"):
                cols.append(c)

    # Drop any accidental future labels
    banned = ("lead_", "target_", "future_")
    cols = [c for c in cols if not any(b in c.lower() for b in banned)]
    if not cols:
        raise ValueError("no usable feature columns found for XGBoost")
    return cols


def load_feature_frame(
    parquet_path: str | Path,
    *,
    metadata_path: str | Path | None = None,
) -> tuple[pd.DataFrame, list[str] | None]:
    """Load the documented feature dataset parquet (+ optional metadata features)."""
    path = Path(parquet_path)
    frame = pd.read_parquet(path)
    features: list[str] | None = None
    meta_path = (
        Path(metadata_path)
        if metadata_path is not None
        else path.parent / f"{path.stem}.metadata.json"
    )
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        features = list(meta.get("feature_columns") or [])
    return frame, features


def prepare_supervised_xy(
    frame: pd.DataFrame,
    *,
    target_col: str,
    feature_columns: Sequence[str],
    time_col: str = "observed_hour",
    group_col: str = "station_id",
    split_spec: ChronologicalSplitSpec | None = None,
) -> pd.DataFrame:
    """Chronological split + drop rows with missing target or all-NaN features."""
    if target_col not in frame.columns:
        raise KeyError(
            f"target {target_col!r} missing; available targets: "
            + ", ".join(c for c in frame.columns if c.startswith("target_"))
        )
    work = frame.copy()
    work[time_col] = pd.to_datetime(work[time_col], utc=True)
    work = assign_chronological_split(work, time_col=time_col, spec=split_spec)
    work = work.sort_values([group_col, time_col], kind="mergesort").reset_index(drop=True)
    work = work.dropna(subset=[target_col])
    # Keep rows with at least one finite feature
    feat = work[list(feature_columns)]
    work = work.loc[feat.notna().any(axis=1)].copy()
    return work


def _fit_one(
    xgb: Any,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    params: XgbHyperParams,
    *,
    early_stopping_rounds: int,
    random_state: int,
    n_jobs: int,
) -> tuple[Any, float, int | None]:
    model = xgb.XGBRegressor(
        objective="reg:squarederror",
        max_depth=params.max_depth,
        learning_rate=params.learning_rate,
        n_estimators=params.n_estimators,
        min_child_weight=params.min_child_weight,
        subsample=params.subsample,
        colsample_bytree=params.colsample_bytree,
        reg_lambda=params.reg_lambda,
        random_state=random_state,
        n_jobs=n_jobs,
        early_stopping_rounds=early_stopping_rounds,
    )
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    pred = model.predict(X_val)
    scores = score_predictions(y_val.to_numpy(), pred)
    best_iter = getattr(model, "best_iteration", None)
    return model, scores.mae, best_iter


def tune_and_fit(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    target_col: str,
    config: XgbConfig,
) -> tuple[Any, XgbHyperParams, float, int | None]:
    """Fit each small candidate with early stopping; keep best validation MAE."""
    xgb = _require_xgboost()
    X_train = train[list(feature_columns)]
    y_train = train[target_col]
    X_val = validation[list(feature_columns)]
    y_val = validation[target_col]

    if X_val.empty or y_val.empty:
        # Fall back: train-only with first candidate, no early stopping eval
        params = config.candidates[0]
        model = xgb.XGBRegressor(
            objective="reg:squarederror",
            max_depth=params.max_depth,
            learning_rate=params.learning_rate,
            n_estimators=params.n_estimators,
            min_child_weight=params.min_child_weight,
            subsample=params.subsample,
            colsample_bytree=params.colsample_bytree,
            reg_lambda=params.reg_lambda,
            random_state=config.random_state,
            n_jobs=config.n_jobs,
        )
        model.fit(X_train, y_train, verbose=False)
        return model, params, float("nan"), None

    best_model = None
    best_params = config.candidates[0]
    best_mae = float("inf")
    best_iter: int | None = None

    for params in config.candidates:
        logger.info("xgb_candidate %s", asdict(params))
        try:
            model, mae, iteration = _fit_one(
                xgb,
                X_train,
                y_train,
                X_val,
                y_val,
                params,
                early_stopping_rounds=config.early_stopping_rounds,
                random_state=config.random_state,
                n_jobs=config.n_jobs,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "xgb_candidate_failed error=%s detail=%s",
                type(exc).__name__,
                exc,
            )
            continue
        logger.info("xgb_candidate_mae=%s best_iteration=%s", mae, iteration)
        if mae < best_mae:
            best_mae = mae
            best_model = model
            best_params = params
            best_iter = iteration

    if best_model is None:
        raise RuntimeError("all XGBoost candidates failed to fit")

    # Refit on train+validation using trees selected by early stopping (no re-tuning).
    X_fit = pd.concat([X_train, X_val], axis=0)
    y_fit = pd.concat([y_train, y_val], axis=0)
    n_trees = int(best_iter) + 1 if best_iter is not None else int(best_params.n_estimators)
    final = xgb.XGBRegressor(
        objective="reg:squarederror",
        max_depth=best_params.max_depth,
        learning_rate=best_params.learning_rate,
        n_estimators=n_trees,
        min_child_weight=best_params.min_child_weight,
        subsample=best_params.subsample,
        colsample_bytree=best_params.colsample_bytree,
        reg_lambda=best_params.reg_lambda,
        random_state=config.random_state,
        n_jobs=config.n_jobs,
    )
    final.fit(X_fit, y_fit, verbose=False)
    logger.info(
        "xgb_selected params=%s val_mae=%s best_iteration=%s n_trees=%s",
        asdict(best_params),
        best_mae,
        best_iter,
        n_trees,
    )
    return final, best_params, best_mae, best_iter


def _reference_predictions_for_lead(
    frame: pd.DataFrame,
    *,
    value_col: str,
    group_col: str,
    time_col: str,
    season: int,
) -> tuple[pd.Series, pd.Series]:
    """Naive / seasonal-naive predictors of y_{T+h} from information at T.

    For horizon=1:
    - naive: y_T
    - seasonal: y_{T+1-season} == value at T-(season-1)
    """
    naive = pd.Series(index=frame.index, dtype="float64")
    seasonal = pd.Series(index=frame.index, dtype="float64")
    for _, group in frame.groupby(group_col, sort=False):
        g = group.sort_values(time_col, kind="mergesort")
        y = g[value_col].astype("float64")
        naive.loc[g.index] = y.to_numpy()
        seasonal.loc[g.index] = y.shift(max(season - 1, 1)).to_numpy()
    return naive, seasonal


def _sarima_lead_predictions(
    frame: pd.DataFrame,
    *,
    value_col: str,
    group_col: str,
    time_col: str,
    train_mask: pd.Series,
    test_mask: pd.Series,
    config: XgbConfig,
) -> pd.Series:
    """SARIMA 1-step predictions at T+h, indexed by origin rows T in ``frame``."""
    preds = pd.Series(index=frame.index, dtype="float64")
    min_train = max(config.sarima_seasonal_order[3] * 2, 24)
    for station, group in frame.groupby(group_col, sort=False):
        g = group.sort_values(time_col, kind="mergesort")
        times = pd.to_datetime(g[time_col], utc=True)
        y = pd.Series(
            g[value_col].astype("float64").to_numpy(),
            index=pd.DatetimeIndex(times),
            name=value_col,
        )
        # Drop duplicate timestamps within a station if any
        y = y[~y.index.duplicated(keep="last")].sort_index()
        tr_mask = train_mask.reindex(g.index).fillna(False).astype(bool)
        te_mask = test_mask.reindex(g.index).fillna(False).astype(bool)
        train_times = pd.DatetimeIndex(times.loc[tr_mask])
        test_origins = list(zip(g.index[te_mask], times.loc[te_mask], strict=False))
        if len(train_times) < min_train or not test_origins:
            continue
        y_train = y.reindex(train_times).dropna()
        if len(y_train) < min_train:
            continue
        eval_times: list[pd.Timestamp] = []
        origin_positions: list[Any] = []
        for pos, t0 in test_origins:
            t1 = pd.Timestamp(t0) + pd.Timedelta(hours=config.horizon)
            if t1 in y.index and pd.notna(y.loc[t1]):
                eval_times.append(t1)
                origin_positions.append(pos)
        if not eval_times:
            continue
        y_eval = y.loc[eval_times]
        try:
            sarima_cfg = SarimaConfig(
                order=config.sarima_order,
                seasonal_order=config.sarima_seasonal_order,
                horizon=1,
                target_col=value_col,
                maxiter=80,
            )
            fitted = fit_sarima(y_train, sarima_cfg)
            pred_at_t1 = one_step_predictions(fitted, y_train, y_eval)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sarima_comparison_failed station=%s error=%s",
                station,
                type(exc).__name__,
            )
            continue
        for pos, t1 in zip(origin_positions, eval_times, strict=False):
            if t1 in pred_at_t1.index and pd.notna(pred_at_t1.loc[t1]):
                preds.loc[pos] = float(pred_at_t1.loc[t1])
    return preds


def feature_importance_frame(model: Any, feature_columns: Sequence[str]) -> pd.DataFrame:
    """Gain / weight importance table sorted descending."""
    booster = model.get_booster()
    score = booster.get_score(importance_type="gain")
    rows = []
    for i, name in enumerate(feature_columns):
        # XGBoost may name features f0,f1,... or use column names
        gain = score.get(name, score.get(f"f{i}", 0.0))
        rows.append({"feature": name, "importance_gain": float(gain)})
    out = pd.DataFrame(rows).sort_values("importance_gain", ascending=False)
    out["rank"] = np.arange(1, len(out) + 1)
    return out.reset_index(drop=True)


def run_xgboost_experiment(
    frame: pd.DataFrame,
    *,
    config: XgbConfig | None = None,
    feature_columns: Sequence[str] | None = None,
    split_spec: ChronologicalSplitSpec | None = None,
    output_dir: str | Path | None = None,
    run_name: str = "xgboost",
    log_mlflow: bool = True,
    mlflow_tracking_uri: str | None = None,
) -> XgbFitResult:
    """Train XGBoost on causal features; compare to naive / seasonal / SARIMA."""
    t0 = time.perf_counter()
    cfg = config or XgbConfig()
    feats = select_feature_columns(frame, feature_columns=feature_columns)
    prepared = prepare_supervised_xy(
        frame,
        target_col=cfg.target_col,
        feature_columns=feats,
        split_spec=split_spec,
    )

    train = prepared.loc[prepared["split"] == "train"]
    validation = prepared.loc[prepared["split"] == "validation"]
    test = prepared.loc[prepared["split"] == "test"]
    if train.empty or test.empty:
        raise ValueError("train or test split is empty after dropping NA targets")

    model, best_params, val_mae, best_iter = tune_and_fit(
        train,
        validation if not validation.empty else train.iloc[:0],
        feature_columns=feats,
        target_col=cfg.target_col,
        config=cfg,
    )

    X_test = test[feats]
    y_test = test[cfg.target_col]
    xgb_pred = pd.Series(model.predict(X_test), index=test.index, name="y_pred_xgboost")

    naive_all, seasonal_all = _reference_predictions_for_lead(
        prepared,
        value_col=cfg.value_col,
        group_col="station_id",
        time_col="observed_hour",
        season=cfg.seasonal_period,
    )
    naive_pred = naive_all.reindex(test.index)
    seasonal_pred = seasonal_all.reindex(test.index)

    metrics = EvaluationTable()
    model_name = f"xgboost_h{cfg.horizon}"
    metrics.rows.append(
        evaluate_predictions(
            test,
            y_true=y_test,
            y_pred=xgb_pred,
            model=model_name,
            split="test",
            target=cfg.target_col,
            horizon=cfg.horizon,
            notes="supervised_feature_model",
            mape_epsilon=cfg.mape_epsilon,
        )
    )
    metrics.rows.append(
        evaluate_predictions(
            test,
            y_true=y_test,
            y_pred=naive_pred,
            model=baseline_name(NAIVE_LAST_VALUE, horizon=cfg.horizon),
            split="test",
            target=cfg.target_col,
            horizon=cfg.horizon,
            notes="reference_baseline",
            mape_epsilon=cfg.mape_epsilon,
        )
    )

    n_times = int(prepared["observed_hour"].nunique())
    if enough_history_for_seasonal(n_times, season=cfg.seasonal_period):
        metrics.rows.append(
            evaluate_predictions(
                test,
                y_true=y_test,
                y_pred=seasonal_pred,
                model=baseline_name(SEASONAL_NAIVE, season=cfg.seasonal_period),
                split="test",
                target=cfg.target_col,
                horizon=cfg.horizon,
                notes=f"season={cfg.seasonal_period}",
                mape_epsilon=cfg.mape_epsilon,
            )
        )

    sarima_pred = pd.Series(index=test.index, dtype="float64")
    if cfg.include_sarima_comparison:
        fit_mask = prepared["split"].isin(["train", "validation"])
        test_mask = prepared["split"] == "test"
        sarima_pred = _sarima_lead_predictions(
            prepared,
            value_col=cfg.value_col,
            group_col="station_id",
            time_col="observed_hour",
            train_mask=fit_mask,
            test_mask=test_mask,
            config=cfg,
        ).reindex(test.index)
        if sarima_pred.notna().any():
            metrics.rows.append(
                evaluate_predictions(
                    test,
                    y_true=y_test,
                    y_pred=sarima_pred,
                    model="sarima_reference",
                    split="test",
                    target=cfg.target_col,
                    horizon=cfg.horizon,
                    notes="one_step_at_T+h",
                    mape_epsilon=cfg.mape_epsilon,
                )
            )

    importance = feature_importance_frame(model, feats)

    pred_frame = pd.DataFrame(
        {
            "station_id": test["station_id"].to_numpy(),
            "observed_hour": test["observed_hour"].to_numpy(),
            "y_true": y_test.to_numpy(),
            "y_pred_xgboost": xgb_pred.to_numpy(),
            "y_pred_naive": naive_pred.to_numpy(),
            "y_pred_seasonal_naive": seasonal_pred.to_numpy(),
            "y_pred_sarima": sarima_pred.reindex(test.index).to_numpy(),
            "split": "test",
            "target": cfg.target_col,
            "horizon": cfg.horizon,
        }
    )

    # Measured comparison only — no pre-claimed winner
    by_model = {r.model: r for r in metrics.rows if r.n_obs > 0}
    xgb_mae = by_model.get(model_name)
    comparison = {
        "xgboost_mae": xgb_mae.mae if xgb_mae else None,
        "naive_mae": next((r.mae for m, r in by_model.items() if m.startswith("naive_")), None),
        "seasonal_naive_mae": next(
            (r.mae for m, r in by_model.items() if m.startswith("seasonal_")), None
        ),
        "sarima_mae": next((r.mae for m, r in by_model.items() if m.startswith("sarima")), None),
    }
    measured = {
        k: v
        for k, v in comparison.items()
        if v is not None and v == v  # drop NaN
    }
    best_key = min(measured, key=measured.get) if measured else None

    metadata: dict[str, Any] = {
        "created_at_utc": datetime.now(tz=UTC).isoformat(),
        "model": model_name,
        "target_col": cfg.target_col,
        "value_col": cfg.value_col,
        "horizon": cfg.horizon,
        "feature_columns": list(feats),
        "n_features": len(feats),
        "best_params": asdict(best_params),
        "best_iteration": best_iter,
        "validation_mae_during_tuning": val_mae,
        "early_stopping_rounds": cfg.early_stopping_rounds,
        "n_train": int(len(train)),
        "n_validation": int(len(validation)),
        "n_test": int(len(test)),
        "metrics": metrics.to_dicts(),
        "mae_comparison": comparison,
        "lowest_mae_among_measured": best_key,
        "note": (
            "Do not claim XGBoost accuracy or superiority unless measured metrics "
            "in this file support it."
        ),
        "config": {
            "target_col": cfg.target_col,
            "horizon": cfg.horizon,
            "candidates": [asdict(c) for c in cfg.candidates],
            "random_state": cfg.random_state,
        },
    }

    training_duration_seconds = time.perf_counter() - t0
    metadata["training_duration_seconds"] = training_duration_seconds

    logger.info("xgb_params %s", json.dumps(asdict(best_params), default=str))
    logger.info("xgb_metrics %s", json.dumps(metrics.to_dicts(), default=str))
    logger.info("xgb_mae_comparison %s best=%s", comparison, best_key)

    result = XgbFitResult(
        model=model,
        model_name=model_name,
        config=cfg,
        best_params=asdict(best_params),
        feature_columns=list(feats),
        feature_importance=importance,
        predictions=pred_frame,
        metrics_table=metrics,
        metadata=metadata,
        best_iteration=best_iter,
    )

    artifact_dir = Path(output_dir) if output_dir is not None else None
    if artifact_dir is None and log_mlflow:
        artifact_dir = Path("ml/training/artifacts/xgboost")
    paths: dict[str, Path] = {}
    if artifact_dir is not None:
        paths = save_xgboost_artifacts(result, artifact_dir, run_name=run_name)

    if log_mlflow and paths and xgb_mae is not None:
        mlflow_metrics: dict[str, float] = {
            "MAE": float(xgb_mae.mae),
            "RMSE": float(xgb_mae.rmse),
            "training_duration": float(training_duration_seconds),
        }
        if xgb_mae.mape is not None and xgb_mae.mape == xgb_mae.mape:
            mlflow_metrics["MAPE"] = float(xgb_mae.mape)
        for key, value in comparison.items():
            if value is not None and value == value:
                mlflow_metrics[key] = float(value)

        lag_cols = [c for c in feats if "_lag_" in c]
        wx_cols = [c for c in feats if c.startswith("wx_")]
        time_cols = [c for c in feats if c.startswith("feat_")]
        log_training_run(
            TrainingRunSpec(
                model_type="xgboost",
                target=cfg.target_col,
                horizon=cfg.horizon,
                parameters={
                    **asdict(best_params),
                    "best_iteration": best_iter,
                    "early_stopping_rounds": cfg.early_stopping_rounds,
                    "random_state": cfg.random_state,
                    "value_col": cfg.value_col,
                    "n_candidates_tuned": len(cfg.candidates),
                },
                feature_configuration={
                    "kind": "causal_feature_dataset",
                    "n_features": len(feats),
                    "include_lags": bool(lag_cols),
                    "include_weather": bool(wx_cols),
                    "include_time": bool(time_cols),
                    "n_lag_features": len(lag_cols),
                    "n_weather_features": len(wx_cols),
                    "n_time_features": len(time_cols),
                    "feature_columns": list(feats),
                    "source": "feature_dataset",
                },
                metrics=mlflow_metrics,
                artifact_paths={
                    "model": paths["model"],
                    "predictions": paths["predictions"],
                    "evaluation_report": paths["metrics_md"],
                    "metrics_csv": paths["metrics_csv"],
                    "feature_importance": paths["feature_importance"],
                },
                tags={"value_col": cfg.value_col},
                run_name=run_name_for(
                    "xgboost",
                    cfg.target_col,
                    cfg.horizon,
                    suffix=run_name if run_name != "xgboost" else None,
                ),
            ),
            tracking_uri=mlflow_tracking_uri,
            enabled=True,
        )

    return result


def save_xgboost_artifacts(
    result: XgbFitResult,
    output_dir: str | Path,
    *,
    run_name: str = "xgboost",
) -> dict[str, Path]:
    """Save model, predictions, metrics, feature importance, and metadata."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    model_path = out / f"{run_name}_model.json"
    result.model.save_model(model_path)

    pred_path = out / f"{run_name}_predictions.parquet"
    result.predictions.to_parquet(pred_path, index=False)

    importance_path = out / f"{run_name}_feature_importance.csv"
    result.feature_importance.to_csv(importance_path, index=False)

    meta_path = out / f"{run_name}_metadata.json"
    meta_path.write_text(
        json.dumps(result.metadata, indent=2, default=str) + "\n", encoding="utf-8"
    )

    metrics_md = out / f"{run_name}_metrics.md"
    metrics_csv = out / f"{run_name}_metrics.csv"
    best = result.metadata.get("lowest_mae_among_measured")
    metrics_md.write_text(
        f"# XGBoost evaluation\n\n"
        f"Model: `{result.model_name}`  \n"
        f"Target: `{result.config.target_col}`  \n"
        f"Lowest measured MAE key: **{best}** "
        f"(only claim a winner from measured rows)\n\n"
        f"{format_evaluation_table(result.metrics_table)}\n",
        encoding="utf-8",
    )
    result.metrics_table.to_dataframe().to_csv(metrics_csv, index=False)

    logger.info(
        "xgb_artifacts_saved model=%s predictions=%s importance=%s metadata=%s",
        model_path,
        pred_path,
        importance_path,
        meta_path,
    )
    return {
        "model": model_path,
        "predictions": pred_path,
        "feature_importance": importance_path,
        "metadata": meta_path,
        "metrics_md": metrics_md,
        "metrics_csv": metrics_csv,
    }
