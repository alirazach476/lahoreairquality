# ML inference

Reusable forecast API for the Lahore AQI platform.

## Design

| Step | Behavior |
|------|----------|
| Load model | Latest (or named) XGBoost artifacts under `ml/training/artifacts/xgboost/` |
| Observations | Mart-shaped recent history (`station_id`, `observed_hour`, AQ + weather) |
| Features | **`build_feature_dataset`** — same module as training (anti-skew) |
| Predict | Model `feature_columns` from training metadata, in that order |
| Output | Forecast timestamps + `y_pred` + model version / metadata |
| Validation | Schema checks; clear `InsufficientHistoryError` when history is too short |

## Usage

```python
from lahore_aqi_ml.inference import forecast, load_model_bundle

bundle = load_model_bundle(artifact_dir="ml/training/artifacts/xgboost")
result = forecast(recent_mart_frame, model=bundle)

print(result.model_version)
print(result.forecasts[["station_id", "forecast_hour", "y_pred"]])
```

Or resolve the latest model inside `forecast(...)`:

```python
result = forecast(recent_mart_frame, artifact_dir="ml/training/artifacts/xgboost")
```

## Output schema

| Column | Meaning |
|--------|---------|
| `station_id` | Station key |
| `origin_hour` | Last observation hour used as feature origin |
| `forecast_hour` | `origin_hour + horizon` |
| `y_pred` | Predicted target value |
| `horizon` | Forecast horizon (hours) |
| `target` | Training target column name |
| `model_type` | e.g. `xgboost` |
| `model_version` | Stable id from metadata timestamp + model name |

`ForecastResult.metadata` includes artifact paths and selected training metadata.

## Insufficient history

Minimum hours ≈ `max(lag, rolling_window) + 1` from the trained feature list
(default lag/roll 24 → **25** hours). Short series raise
`InsufficientHistoryError` with the required vs available counts.
