# ml/inference

Job notes / configs (optional). Library code lives in
`ml/src/lahore_aqi_ml/inference/`.

```python
from lahore_aqi_ml.inference import forecast, load_model_bundle

bundle = load_model_bundle(artifact_dir="ml/training/artifacts/xgboost")
result = forecast(recent_observations, model=bundle)
```

Docs: [`docs/ml-inference.md`](../docs/ml-inference.md).
