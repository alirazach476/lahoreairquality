"""Reusable forecast API: load model → features → predict → schema'd result."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from lahore_aqi_ml.features.pipeline import FeatureBuildConfig
from lahore_aqi_ml.inference.exceptions import InputValidationError
from lahore_aqi_ml.inference.features import (
    assert_sufficient_history,
    build_inference_features,
    origin_feature_matrix,
    required_history_hours,
)
from lahore_aqi_ml.inference.registry import LoadedModel, load_model_bundle
from lahore_aqi_ml.inference.validate import validate_observations

logger = logging.getLogger(__name__)

FORECAST_COLUMNS = (
    "station_id",
    "origin_hour",
    "forecast_hour",
    "y_pred",
    "horizon",
    "target",
    "model_type",
    "model_version",
)


@dataclass
class ForecastResult:
    """Point forecasts plus model identity / metadata."""

    forecasts: pd.DataFrame
    model_version: str
    model_type: str
    target: str
    horizon: int
    feature_columns: list[str]
    origin_hours: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)
    required_history_hours: int = 0

    def to_frame(self) -> pd.DataFrame:
        return self.forecasts.copy()

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "model_type": self.model_type,
            "target": self.target,
            "horizon": self.horizon,
            "feature_columns": list(self.feature_columns),
            "origin_hours": dict(self.origin_hours),
            "required_history_hours": self.required_history_hours,
            "n_forecasts": int(len(self.forecasts)),
            "forecasts": self.forecasts.to_dict(orient="records"),
            "metadata": dict(self.metadata),
        }


def forecast(
    observations: pd.DataFrame,
    *,
    model: LoadedModel | None = None,
    artifact_dir: str | None = None,
    artifact_root: str | None = None,
    run_name: str | None = None,
    station_ids: Sequence[str] | None = None,
    as_of: pd.Timestamp | str | None = None,
    feature_config: FeatureBuildConfig | None = None,
) -> ForecastResult:
    """Produce horizon-ahead forecasts from recent mart-shaped observations.

    Feature generation uses ``build_feature_dataset`` (shared with training).
    Model feature columns come from training metadata to prevent skew.
    """
    bundle = model or load_model_bundle(
        artifact_dir=artifact_dir,
        artifact_root=artifact_root,
        model_type="xgboost",
        run_name=run_name,
    )
    obs = validate_observations(observations)
    as_of_ts = None if as_of is None else pd.Timestamp(as_of)
    if as_of_ts is not None and as_of_ts.tzinfo is None:
        as_of_ts = as_of_ts.tz_localize("UTC")

    need = required_history_hours(bundle.feature_columns, config=feature_config)
    assert_sufficient_history(
        obs,
        feature_columns=bundle.feature_columns,
        station_ids=station_ids,
        min_hours=need,
    )

    # Shared training feature pipeline
    dataset = build_inference_features(obs, config=feature_config)
    # Guard: trained columns must be a subset of (or equal to) built columns
    built = set(dataset.feature_columns)
    missing_built = [
        c for c in bundle.feature_columns if c not in built and c not in dataset.frame.columns
    ]
    if missing_built:
        raise InputValidationError(
            "training-serving skew: model features not produced by "
            f"build_feature_dataset: {missing_built[:15]}"
        )

    origins = origin_feature_matrix(
        dataset,
        bundle.feature_columns,
        station_ids=station_ids,
        as_of=as_of_ts,
    )
    X = origins[list(bundle.feature_columns)]
    preds = np.asarray(bundle.model.predict(X), dtype="float64")

    horizon = int(bundle.horizon)
    origin_hours = pd.to_datetime(origins["observed_hour"], utc=True)
    forecast_hours = origin_hours + pd.to_timedelta(horizon, unit="h")

    forecasts = pd.DataFrame(
        {
            "station_id": origins["station_id"].astype(str).to_numpy(),
            "origin_hour": origin_hours.to_numpy(),
            "forecast_hour": forecast_hours.to_numpy(),
            "y_pred": preds,
            "horizon": horizon,
            "target": bundle.target_col,
            "model_type": bundle.model_type,
            "model_version": bundle.model_version,
        }
    )
    # Enforce schema column order
    forecasts = forecasts.loc[:, list(FORECAST_COLUMNS)]

    origin_map = {
        str(row.station_id): pd.Timestamp(row.origin_hour).isoformat()
        for row in forecasts.itertuples(index=False)
    }

    meta = {
        "model_path": str(bundle.model_path),
        "metadata_path": str(bundle.metadata_path),
        "created_at_utc": bundle.created_at_utc,
        "best_params": bundle.extra.get("best_params"),
        "best_iteration": bundle.extra.get("best_iteration"),
        "value_col": bundle.extra.get("value_col"),
        "training_metadata": {
            k: bundle.metadata.get(k)
            for k in (
                "n_train",
                "n_validation",
                "n_test",
                "mae_comparison",
                "lowest_mae_among_measured",
            )
            if k in bundle.metadata
        },
    }

    logger.info(
        "forecast_done model_version=%s n=%s horizon=%s",
        bundle.model_version,
        len(forecasts),
        horizon,
    )
    return ForecastResult(
        forecasts=forecasts,
        model_version=bundle.model_version,
        model_type=bundle.model_type,
        target=bundle.target_col,
        horizon=horizon,
        feature_columns=list(bundle.feature_columns),
        origin_hours=origin_map,
        metadata=meta,
        required_history_hours=need,
    )


def forecast_from_latest_model(
    observations: pd.DataFrame,
    **kwargs: Any,
) -> ForecastResult:
    """Convenience wrapper: always resolve the latest artifact bundle."""
    kwargs.pop("model", None)
    return forecast(observations, model=None, **kwargs)
