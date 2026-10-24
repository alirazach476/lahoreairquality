# lahore_aqi_ml.inference

Load trained XGBoost models, build features with the **same**
`build_feature_dataset` pipeline used in training, and emit point forecasts.

```python
from lahore_aqi_ml.inference import forecast

result = forecast(observations_df, artifact_dir="ml/training/artifacts/xgboost")
```

See [`docs/ml-inference.md`](../../../../docs/ml-inference.md).
