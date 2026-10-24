# `lahore_aqi_ml.evaluation`

Chronological train / validation / test evaluation for Lahore AQI forecasts.

- **No shuffling** — splits cut on sorted unique `observed_hour` values.
- **Baselines** — `naive_last_value` and `seasonal_naive` (season=24 by default).
- **Metrics** — MAE, RMSE, MAPE (MAPE skips near-zero actuals).
- **Reusable** — `evaluate_predictions` / `PointForecaster` for SARIMA and XGBoost later.

SARIMA and XGBoost are **not** implemented here.
