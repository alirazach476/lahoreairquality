# SARIMA forecasting

Univariate SARIMA on the project hourly target (default **`pm25`** from
`mart_air_quality_features` / feature frames). Configurable via `SarimaConfig`.

| Piece | Location |
|-------|----------|
| Library | `ml/src/lahore_aqi_ml/training/sarima.py` |
| Data prep | `ml/src/lahore_aqi_ml/training/data.py` |
| CLI | `ml/training/sarima.py` |
| Evaluation | reuses `lahore_aqi_ml.evaluation` |

## Rules

- Chronological train / validation / test — **no shuffle**.
- Seasonal period default **`s=24`** (hourly diurnal).
- Orders are configurable; optional selection uses a **small** candidate list only.
- Test metrics: MAE, RMSE, MAPE (near-zero actuals skipped).
- Always compared to **naive last-value** on the same test window.
- Predictions + metadata saved for visualization / logging.

Do **not** claim SARIMA is better unless `comparison_vs_naive_mae == "sarima"`.

MLflow logging is on by default (`lahore-aqi/sarima`). See [`docs/ml-mlflow.md`](ml-mlflow.md).
