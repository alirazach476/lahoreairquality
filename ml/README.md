# ml/

Machine learning lifecycle for Lahore AQI forecasting.

| Area | Role |
|------|------|
| `features/` | Feature engineering from warehouse marts |
| `training/` | SARIMA, XGBoost (+ baselines via evaluation) |
| `evaluation/` | Metrics, comparison, and reporting helpers |
| `tracking/` | MLflow experiment logging |
| `inference/` | Load models, shared features, forecasts |

**Status:** features, baselines, SARIMA, XGBoost, MLflow tracking, and
**inference** are implemented.

## MLflow (quick start)

Tracking URI is **not** hard-coded: use `MLFLOW_TRACKING_URI` or
`--mlflow-tracking-uri`. If unset, runs log to a local `./mlruns` store.

```bash
pip install -e "./ml[dev]"
# optional: set MLFLOW_TRACKING_URI=sqlite:///mlflow.db
python ml/training/train_xgboost.py --from-features ml/features/datasets/lahore_aqi_features.parquet -v
mlflow ui --backend-store-uri sqlite:///mlflow.db
```

See [`docs/ml-mlflow.md`](../docs/ml-mlflow.md) and [`training/README.md`](training/README.md).

Also: [`docs/ml-features.md`](../docs/ml-features.md), [`docs/ml-evaluation.md`](../docs/ml-evaluation.md),
[`docs/ml-sarima.md`](../docs/ml-sarima.md), [`docs/ml-xgboost.md`](../docs/ml-xgboost.md),
[`docs/ml-inference.md`](../docs/ml-inference.md).
