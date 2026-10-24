# lahore_aqi_ml.features

Reusable, time-aware feature generators for Lahore AQI forecasting.

| Module | Role |
|--------|------|
| `columns` | Inspected mart column inventory |
| `lags` | Causal lags (1/2/3/6/12/24) |
| `rolling` | Causal rolling mean/std/min/max |
| `weather` | Same-hour weather (+ wind cyclic) |
| `calendar` | Hour, DOW, month, weekend |
| `targets` | Future leads (labels only) |
| `pipeline` | `build_feature_dataset` |
| `dataset` | Save parquet + documentation |
| `leakage` | Assertion helpers for tests |

CLI / datasets: `ml/features/`.
