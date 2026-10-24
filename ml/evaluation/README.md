# ml/evaluation

Time-series evaluation workspace for Lahore AQI forecasting baselines.

**Implementation:** `lahore_aqi_ml.evaluation` (`ml/src/lahore_aqi_ml/evaluation/`).  
**Docs:** [`docs/ml-evaluation.md`](../../docs/ml-evaluation.md).

## Rules

1. Chronological train / validation / test split only — **never** shuffle.
2. Baseline reference models: last-value naive + seasonal naive (when history allows).
3. Metrics: MAE, RMSE, MAPE (MAPE undefined / skipped for near-zero actuals).
4. Always report `n_obs` (and `n_mape` when MAPE applies).
5. Future SARIMA / XGBoost must reuse this framework and beat these baselines.

## Run baselines

```bash
pip install -e "./ml[dev]"
# Demo series (explicit synthetic — not production observations):
python ml/evaluation/run_baselines.py --synthetic
# Or from a feature / mart parquet with station_id, observed_hour, and a value column:
python ml/evaluation/run_baselines.py --from-parquet path/to/frame.parquet --value-col pm25
```

Artifacts (optional): `ml/evaluation/reports/`.
