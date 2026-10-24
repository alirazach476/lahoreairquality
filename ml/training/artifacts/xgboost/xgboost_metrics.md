# XGBoost evaluation

Model: `xgboost_h1`  
Target: `target_pm25_lead_1`  
Lowest measured MAE key: **xgboost_mae** (only claim a winner from measured rows)

| model | split | target | horizon | mae | rmse | mape | n_obs | n_mape | mape_skipped_near_zero | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| xgboost_h1 | test | target_pm25_lead_1 | 1 | 2.8099 | 3.2844 | 0.1450 | 35 | 35 | 0 | supervised_feature_model |
| naive_last_value_h1 | test | target_pm25_lead_1 | 1 | 6.0179 | 7.0237 | 0.2573 | 35 | 35 | 0 | reference_baseline |
| seasonal_naive_s24 | test | target_pm25_lead_1 | 1 | 3.4664 | 4.1134 | 0.1797 | 35 | 35 | 0 | season=24 |
| sarima_reference | test | target_pm25_lead_1 | 1 | 4.1800 | 4.9832 | 0.1955 | 34 | 34 | 0 | one_step_at_T+h |
