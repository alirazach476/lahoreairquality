"""MLflow helpers for Lahore AQI training runs.

Tracking URI is never hard-coded. Resolution order:

1. Explicit ``tracking_uri`` argument (e.g. CLI ``--mlflow-tracking-uri``)
2. Environment variable ``MLFLOW_TRACKING_URI``
3. MLflow's own default (local ``./mlruns`` file store)

Works with a local file store or a remote tracking server the same way.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Consistent experiment naming: lahore-aqi/<model_family>
EXPERIMENT_PREFIX = "lahore-aqi"
TRACKING_URI_ENV = "MLFLOW_TRACKING_URI"


@dataclass(frozen=True, slots=True)
class TrainingRunSpec:
    """Payload logged for one training experiment run."""

    model_type: str
    target: str
    horizon: int
    parameters: Mapping[str, Any]
    metrics: Mapping[str, float]
    artifact_paths: Mapping[str, Path]
    feature_configuration: Mapping[str, Any] | None = None
    tags: Mapping[str, str] = field(default_factory=dict)
    run_name: str | None = None


def _require_mlflow():
    try:
        import mlflow
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "mlflow is required for experiment tracking. Install with: pip install mlflow"
        ) from exc
    return mlflow


def resolve_tracking_uri(explicit: str | None = None) -> str | None:
    """Resolve tracking URI without embedding a default host/URL in code.

    Returns ``None`` when neither an explicit URI nor ``MLFLOW_TRACKING_URI``
    is set — callers then leave MLflow on its built-in local file store.
    """
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    env = os.environ.get(TRACKING_URI_ENV)
    if env is not None and env.strip():
        return env.strip()
    return None


def configure_mlflow(tracking_uri: str | None = None) -> str:
    """Apply tracking URI if provided via arg/env; return the active URI.

    When no URI is configured, MLflow keeps its built-in local store. MLflow 3+
    requires an explicit opt-in for the legacy file store; we set that env flag
    only when the caller did not supply a URI (local default path). A tracking
    server or ``sqlite:///...`` URI never needs that flag.
    """
    mlflow = _require_mlflow()
    uri = resolve_tracking_uri(tracking_uri)
    if uri is not None:
        mlflow.set_tracking_uri(uri)
        logger.info("mlflow_tracking_uri_set uri=%s", uri)
    else:
        # Local default (./mlruns) — not a hard-coded host/URL.
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        logger.info(
            "mlflow_tracking_uri_default active=%s (set %s or pass tracking_uri for sqlite/server)",
            mlflow.get_tracking_uri(),
            TRACKING_URI_ENV,
        )
    return str(mlflow.get_tracking_uri())


def experiment_name_for(model_type: str) -> str:
    """``lahore-aqi/<model_type>`` — one experiment family per model type."""
    family = model_type.strip().lower().replace(" ", "_")
    if not family:
        raise ValueError("model_type must be non-empty")
    return f"{EXPERIMENT_PREFIX}/{family}"


def run_name_for(
    model_type: str,
    target: str,
    horizon: int,
    *,
    suffix: str | None = None,
) -> str:
    """``<model>__<target>__h<horizon>[__suffix]``."""
    safe_target = target.strip().replace("/", "_").replace(" ", "_")
    base = f"{model_type.strip().lower()}__{safe_target}__h{int(horizon)}"
    if suffix:
        return f"{base}__{suffix.strip()}"
    return base


def _flatten_params(
    params: Mapping[str, Any],
    *,
    prefix: str = "",
) -> dict[str, str]:
    """Flatten nested params to MLflow-safe string values."""
    out: dict[str, str] = {}
    for key, value in params.items():
        name = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if value is None:
            out[name] = ""
        elif isinstance(value, (bool, int, float, str)):
            out[name] = str(value)
        elif isinstance(value, (list, tuple)):
            out[name] = json.dumps(list(value), default=str)
        elif isinstance(value, Mapping):
            out.update(_flatten_params(value, prefix=name))
        else:
            out[name] = str(value)
    return out


def _sanitize_metrics(metrics: Mapping[str, float]) -> dict[str, float]:
    clean: dict[str, float] = {}
    for key, value in metrics.items():
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number != number:  # NaN
            continue
        clean[str(key)] = number
    return clean


def log_training_run(
    spec: TrainingRunSpec,
    *,
    tracking_uri: str | None = None,
    enabled: bool = True,
) -> str | None:
    """Log one training run to MLflow. Returns run_id, or None if disabled."""
    if not enabled:
        logger.info("mlflow_logging_skipped enabled=false")
        return None

    mlflow = _require_mlflow()
    active_uri = configure_mlflow(tracking_uri)
    experiment = experiment_name_for(spec.model_type)
    mlflow.set_experiment(experiment)

    run_name = spec.run_name or run_name_for(spec.model_type, spec.target, spec.horizon)

    params = {
        "model_type": spec.model_type,
        "target": spec.target,
        "forecast_horizon": spec.horizon,
        **dict(spec.parameters),
    }
    if spec.feature_configuration is not None:
        # Compact summary in params; full config logged as JSON artifact.
        feat = spec.feature_configuration
        for key in (
            "n_features",
            "include_lags",
            "include_weather",
            "include_time",
            "source",
            "kind",
            "n_lag_features",
            "n_weather_features",
            "n_time_features",
        ):
            if key in feat:
                params[f"feature_{key}"] = feat[key]

    flat_params = _flatten_params(params)
    metrics = _sanitize_metrics(spec.metrics)

    tags = {
        "project": "lahore-aqi",
        "model_type": spec.model_type,
        "target": spec.target,
        **{str(k): str(v) for k, v in spec.tags.items()},
    }

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags(tags)
        # MLflow param value length limit — truncate very long strings
        for key, value in flat_params.items():
            text = value if len(value) <= 500 else value[:497] + "..."
            mlflow.log_param(key, text)
        for key, value in metrics.items():
            mlflow.log_metric(key, value)

        if spec.feature_configuration is not None:
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                cfg_file = Path(tmp) / "feature_configuration.json"
                cfg_file.write_text(
                    json.dumps(spec.feature_configuration, indent=2, default=str) + "\n",
                    encoding="utf-8",
                )
                mlflow.log_artifact(str(cfg_file), artifact_path="config")

        for label, path in spec.artifact_paths.items():
            p = Path(path)
            if not p.exists():
                logger.warning("mlflow_artifact_missing label=%s path=%s", label, p)
                continue
            # Group by conventional artifact folders
            if label in {"model", "trained_model"}:
                artifact_path = "model"
            elif label in {"predictions"}:
                artifact_path = "predictions"
            elif label in {"evaluation_report", "metrics_md", "metrics_csv"}:
                artifact_path = "evaluation"
            elif label in {"feature_importance"}:
                artifact_path = "feature_importance"
            else:
                artifact_path = "other"
            mlflow.log_artifact(str(p), artifact_path=artifact_path)
            logger.info(
                "mlflow_artifact_logged label=%s path=%s dest=%s",
                label,
                p,
                artifact_path,
            )

        run_id = run.info.run_id
        logger.info(
            "mlflow_run_logged experiment=%s run_name=%s run_id=%s tracking_uri=%s",
            experiment,
            run_name,
            run_id,
            active_uri,
        )
        return run_id
