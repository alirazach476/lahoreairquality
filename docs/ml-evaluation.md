# ML forecast evaluation

Chronological evaluation framework for Lahore AQI forecasts. **Baselines only**
in this phase — SARIMA and XGBoost must reuse the same API later.

| Piece | Location |
|-------|----------|
| Package | `ml/src/lahore_aqi_ml/evaluation/` |
| Workspace / CLI | `ml/evaluation/` |
| Tests | `tests/ml/evaluation/` |

## Split policy

- Sort unique `observed_hour` timestamps ascending.
- Cut into train / validation / test by configured fractions (default 70% / 15% / 15%).
- Assign every panel row by its timestamp.
- **Never** randomly shuffle the series.

## Baselines (reference models)

| Model | Definition |
|-------|------------|
| `naive_last_value_h{H}` | \(\hat y_t = y_{t-H}\) (persistence; H=1 is classic last-value) |
| `seasonal_naive_s{S}` | \(\hat y_t = y_{t-S}\) when enough history exists (default S=24 for hourly) |

If fewer than `S+1` distinct timestamps exist, seasonal naive is reported as
skipped with `n_obs=0` and an explanatory note.

## Metrics

| Metric | Notes |
|--------|--------|
| MAE | Mean absolute error on pairwise-complete rows |
| RMSE | Root mean squared error |
| MAPE | Mean \|error\| / \|actual\| as a **fraction**; rows with \|actual\| ≤ `1e-8` are **excluded**; `n_mape` and `mape_skipped_near_zero` are reported |
| n_obs | Number of pairwise-complete observations used for MAE/RMSE |

## Reuse by future models

```python
from lahore_aqi_ml.evaluation import (
    evaluate_predictions,
    run_baseline_evaluation,
    PointForecaster,
)

# 1) Establish baseline table
table = run_baseline_evaluation(frame, value_col="pm25")

# 2) Score any future model predictions with the same metrics / splits
row = evaluate_predictions(
    test_frame,
    y_true=test_frame["pm25"],
    y_pred=my_model_predictions,
    model="xgboost_h1",
    split="test",
    target="pm25",
    horizon=1,
)
```

Implement `PointForecaster` for SARIMA / XGBoost adapters when those phases land.
Do not train those models in this package yet.
