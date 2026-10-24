# ml/training

Training entrypoints for Lahore AQI forecasts.

| Script / module | Role |
|-----------------|------|
| `sarima.py` | CLI for configurable SARIMA + naive comparison |
| `train_xgboost.py` | CLI for XGBoost on the causal feature dataset |
| `lahore_aqi_ml.training` | Library: data prep, fit, predictions, artifacts |
| `lahore_aqi_ml.tracking` | MLflow experiment logging |

## MLflow

Every training run logs to MLflow by default (disable with `--no-mlflow`).

- **URI:** `--mlflow-tracking-uri` or env `MLFLOW_TRACKING_URI` — never hard-coded.
  If both are unset, MLflow uses the local `./mlruns` file store.
- **Experiments:** `lahore-aqi/sarima`, `lahore-aqi/xgboost`
- **Runs:** `<model>__<target>__h<horizon>`

### View experiments (local)

```bash
# if using recommended SQLite:
#   set MLFLOW_TRACKING_URI=sqlite:///mlflow.db
mlflow ui --backend-store-uri sqlite:///mlflow.db
# or default file store: mlflow ui --backend-store-uri ./mlruns
```

### View experiments (tracking server)

```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
# train as usual; open the server UI in a browser
```

Full details: [`docs/ml-mlflow.md`](../../docs/ml-mlflow.md).

## XGBoost (feature dataset)

```bash
pip install -e "./ml[dev]"

python ml/training/train_xgboost.py \
  --from-features ml/features/datasets/lahore_aqi_features.parquet \
  -v

python ml/training/train_xgboost.py --synthetic -v
```

Artifacts under `ml/training/artifacts/xgboost/` plus the MLflow run.

## SARIMA

```bash
python ml/training/sarima.py --synthetic -v
python ml/training/sarima.py --from-parquet path/to/mart.parquet --station-id S1
```

Only claim SARIMA beats the naive baseline when `comparison_vs_naive_mae` is `sarima`.
