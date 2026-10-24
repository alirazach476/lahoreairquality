# XGBoost forecasting

Supervised point forecasts on the **causal feature dataset**
(`ml/features/datasets/lahore_aqi_features.parquet`).

## Protocol

1. **Target:** default `target_pm25_lead_1` (label at T is PM2.5 at T+1).
2. **Features:** columns from feature metadata — lagged AQ/PM, rolling stats,
   weather (`wx_*`), calendar (`feat_*`). Never `target_*` / lead labels.
3. **Split:** chronological train / validation / test (default 70/15/15).
   No row shuffle; no future observations in training features.
4. **Tuning:** at most a small fixed candidate list (≤12). Validation MAE
   selects the winner; early stopping sets tree count.
5. **Metrics:** MAE, RMSE, MAPE (where denominators allow).
6. **Comparisons on the same test origins:** naive (`y_T`), seasonal naive
   (`y_{T+1-s}`), and SARIMA 1-step at T+1.

## Reproducible command

```bash
pip install -e "./ml[dev]"
python ml/training/train_xgboost.py \
  --from-features ml/features/datasets/lahore_aqi_features.parquet \
  --output-dir ml/training/artifacts/xgboost \
  --run-name xgboost \
  -v
```

Do not claim a specific accuracy or that XGBoost beats baselines until the
written metrics artifacts are inspected.

MLflow logging is on by default (`lahore-aqi/xgboost`). See
[`docs/ml-mlflow.md`](ml-mlflow.md).
