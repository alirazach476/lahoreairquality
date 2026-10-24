# MLflow experiment tracking

Every SARIMA and XGBoost training run can log parameters, metrics, and artifacts
to MLflow. Model fit logic is unchanged; tracking wraps the existing experiment
entrypoints.

## Tracking URI (never hard-coded)

Resolution order:

1. CLI `--mlflow-tracking-uri <uri>`
2. Environment variable `MLFLOW_TRACKING_URI`
3. If neither is set, MLflow’s built-in **local file store** (`./mlruns`)

| Mode | How |
|------|-----|
| Local (default) | Omit URI → MLflow `./mlruns` file store (auto opt-in) |
| Local SQLite | `export MLFLOW_TRACKING_URI=sqlite:///mlflow.db` |
| Tracking server | `export MLFLOW_TRACKING_URI=http://host:5000` |

Disable logging for a single run with `--no-mlflow`.

Recommended local SQLite (survives MLflow 3+ without file-store opt-in):

```bash
export MLFLOW_TRACKING_URI=sqlite:///mlflow.db
```

## Experiment naming

| Item | Convention | Example |
|------|------------|---------|
| Experiment | `lahore-aqi/<model_type>` | `lahore-aqi/sarima`, `lahore-aqi/xgboost` |
| Run name | `<model>__<target>__h<horizon>[__suffix]` | `xgboost__target_pm25_lead_1__h1` |

## What each run records

**Parameters:** model type, target, forecast horizon, feature configuration
summary, hyperparameters (orders / XGB params, etc.).

**Metrics:** MAE, RMSE, MAPE (when defined), `training_duration` (seconds).

**Artifacts:** trained model, predictions, evaluation report (markdown + CSV),
feature importance (XGBoost).

## Viewing experiments

### Local store

```bash
pip install -e "./ml[dev]"
# optional but recommended:
#   set MLFLOW_TRACKING_URI=sqlite:///mlflow.db
# after at least one training run:
mlflow ui --backend-store-uri sqlite:///mlflow.db
# or, if you used the default file store:
#   mlflow ui --backend-store-uri ./mlruns
```

Open the URL printed by the CLI (typically http://127.0.0.1:5000).

### Remote / Docker tracking server

```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
python ml/training/train_xgboost.py --from-features ml/features/datasets/lahore_aqi_features.parquet -v
# UI is served by that tracking server
```

## Example commands

```bash
# Local default store
python ml/training/sarima.py --synthetic -v
python ml/training/train_xgboost.py --from-features ml/features/datasets/lahore_aqi_features.parquet -v

# Explicit server
python ml/training/train_xgboost.py \
  --from-features ml/features/datasets/lahore_aqi_features.parquet \
  --mlflow-tracking-uri http://127.0.0.1:5000 \
  -v

# Skip MLflow
python ml/training/sarima.py --synthetic --no-mlflow
```
