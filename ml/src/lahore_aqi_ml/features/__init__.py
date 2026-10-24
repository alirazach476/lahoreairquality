"""Time-aware ML feature engineering for Lahore AQI forecasting.

Source mart columns: see ``columns.SOURCE_MART`` / ``docs/ml-features.md``.
Features at time T never use information after T.
"""

from lahore_aqi_ml.features.columns import (
    AQ_SERIES_COLUMNS,
    DEFAULT_LAGS,
    DEFAULT_ROLLING_WINDOWS,
    SOURCE_MART,
    WEATHER_COLUMNS,
)
from lahore_aqi_ml.features.dataset import save_feature_dataset
from lahore_aqi_ml.features.pipeline import (
    FeatureBuildConfig,
    FeatureDataset,
    build_feature_dataset,
    validate_mart_columns,
)
from lahore_aqi_ml.features.synthetic import make_synthetic_mart_frame

__all__ = [
    "AQ_SERIES_COLUMNS",
    "DEFAULT_LAGS",
    "DEFAULT_ROLLING_WINDOWS",
    "FeatureBuildConfig",
    "FeatureDataset",
    "SOURCE_MART",
    "WEATHER_COLUMNS",
    "build_feature_dataset",
    "make_synthetic_mart_frame",
    "save_feature_dataset",
    "validate_mart_columns",
]
