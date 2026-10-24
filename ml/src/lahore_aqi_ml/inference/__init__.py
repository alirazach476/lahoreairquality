"""ML inference: load trained models, build shared features, forecast."""

from lahore_aqi_ml.inference.exceptions import (
    InferenceError,
    InputValidationError,
    InsufficientHistoryError,
    ModelNotFoundError,
)
from lahore_aqi_ml.inference.features import (
    build_inference_features,
    required_history_hours,
)
from lahore_aqi_ml.inference.forecast import (
    FORECAST_COLUMNS,
    ForecastResult,
    forecast,
    forecast_from_latest_model,
)
from lahore_aqi_ml.inference.registry import LoadedModel, load_model_bundle

__all__ = [
    "FORECAST_COLUMNS",
    "ForecastResult",
    "InferenceError",
    "InputValidationError",
    "InsufficientHistoryError",
    "LoadedModel",
    "ModelNotFoundError",
    "build_inference_features",
    "forecast",
    "forecast_from_latest_model",
    "load_model_bundle",
    "required_history_hours",
]
