"""Load the latest trained model + metadata from local artifact directories."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from lahore_aqi_ml.inference.exceptions import ModelNotFoundError

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACT_ROOT = Path("ml/training/artifacts")
XGBOOST_SUBDIR = "xgboost"
SARIMA_SUBDIR = "sarima"


@dataclass(frozen=True, slots=True)
class LoadedModel:
    """In-memory model bundle for inference."""

    model_type: str
    model: Any
    metadata: dict[str, Any]
    feature_columns: tuple[str, ...]
    horizon: int
    target_col: str
    model_path: Path
    metadata_path: Path
    model_version: str
    created_at_utc: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _parse_created(meta: dict[str, Any], path: Path) -> datetime:
    raw = meta.get("created_at_utc")
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime)


def _version_string(meta: dict[str, Any], model_path: Path) -> str:
    """Stable version label from metadata (no accuracy claims)."""
    created = meta.get("created_at_utc") or "unknown_time"
    model_name = meta.get("model") or model_path.stem
    # Prefer short stamp for readability
    stamp = str(created).replace(":", "").replace("-", "")[:15]
    return f"{model_name}@{stamp}"


def discover_metadata_files(
    artifact_dir: str | Path,
    *,
    pattern: str = "*_metadata.json",
) -> list[Path]:
    root = Path(artifact_dir)
    if not root.exists():
        return []
    return sorted(root.glob(pattern))


def resolve_latest_artifact_dir(
    *,
    artifact_root: str | Path | None = None,
    model_type: str = "xgboost",
) -> Path:
    """Pick the artifact directory for ``model_type`` under the training tree."""
    root = Path(artifact_root) if artifact_root is not None else DEFAULT_ARTIFACT_ROOT
    sub = XGBOOST_SUBDIR if model_type.lower() == "xgboost" else model_type.lower()
    path = root / sub
    if not path.exists():
        raise ModelNotFoundError(
            f"artifact directory not found for model_type={model_type!r}: {path}"
        )
    return path


def find_latest_run(
    artifact_dir: str | Path,
    *,
    run_name: str | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    """Return ``(model_path, metadata_path, metadata)`` for the newest run.

    Prefers ``{run_name}_metadata.json`` when ``run_name`` is set; otherwise
    chooses the metadata file with the latest ``created_at_utc``.
    """
    root = Path(artifact_dir)
    metas = discover_metadata_files(root)
    if not metas:
        raise ModelNotFoundError(f"no *_metadata.json under {root}")

    if run_name is not None:
        meta_path = root / f"{run_name}_metadata.json"
        if not meta_path.exists():
            raise ModelNotFoundError(f"metadata not found for run_name={run_name!r}: {meta_path}")
        metas = [meta_path]

    best_meta_path: Path | None = None
    best_meta: dict[str, Any] | None = None
    best_created: datetime | None = None
    for path in metas:
        meta = json.loads(path.read_text(encoding="utf-8"))
        created = _parse_created(meta, path)
        if best_created is None or created > best_created:
            best_created = created
            best_meta_path = path
            best_meta = meta

    assert best_meta_path is not None and best_meta is not None
    stem = best_meta_path.name.replace("_metadata.json", "")
    # Prefer JSON booster (xgboost); fall back to pkl (sarima)
    candidates = [
        best_meta_path.parent / f"{stem}_model.json",
        best_meta_path.parent / f"{stem}_model.pkl",
        best_meta_path.parent / f"{stem}_model.ubj",
    ]
    model_path = next((p for p in candidates if p.exists()), None)
    if model_path is None:
        raise ModelNotFoundError(
            f"model file missing for run stem={stem!r} under {root} "
            f"(looked for {', '.join(p.name for p in candidates)})"
        )
    return model_path, best_meta_path, best_meta


def load_xgboost_booster(model_path: Path) -> Any:
    try:
        import xgboost as xgb
    except ImportError as exc:  # pragma: no cover
        raise ImportError("xgboost is required to load XGBoost models") from exc
    model = xgb.XGBRegressor()
    model.load_model(str(model_path))
    return model


def load_model_bundle(
    *,
    artifact_dir: str | Path | None = None,
    artifact_root: str | Path | None = None,
    model_type: str = "xgboost",
    run_name: str | None = None,
) -> LoadedModel:
    """Load the latest (or named) trained model for inference."""
    if model_type.lower() != "xgboost":
        raise ModelNotFoundError(
            f"inference currently supports model_type='xgboost' "
            f"(got {model_type!r}); SARIMA serving is not in this layer"
        )

    directory = (
        Path(artifact_dir)
        if artifact_dir is not None
        else resolve_latest_artifact_dir(artifact_root=artifact_root, model_type=model_type)
    )
    model_path, meta_path, meta = find_latest_run(directory, run_name=run_name)
    feature_columns = list(meta.get("feature_columns") or [])
    if not feature_columns:
        raise ModelNotFoundError(f"metadata at {meta_path} has empty feature_columns; cannot serve")
    horizon = int(meta.get("horizon") or 1)
    target_col = str(meta.get("target_col") or "target_pm25_lead_1")
    model = load_xgboost_booster(model_path)
    version = _version_string(meta, model_path)
    logger.info(
        "model_loaded type=xgboost path=%s version=%s n_features=%s horizon=%s",
        model_path,
        version,
        len(feature_columns),
        horizon,
    )
    return LoadedModel(
        model_type="xgboost",
        model=model,
        metadata=meta,
        feature_columns=tuple(feature_columns),
        horizon=horizon,
        target_col=target_col,
        model_path=model_path,
        metadata_path=meta_path,
        model_version=version,
        created_at_utc=meta.get("created_at_utc"),
        extra={
            "best_params": meta.get("best_params"),
            "best_iteration": meta.get("best_iteration"),
            "value_col": meta.get("value_col"),
        },
    )
