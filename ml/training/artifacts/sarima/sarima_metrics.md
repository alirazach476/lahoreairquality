# SARIMA evaluation

Model: `sarima_o(1, 0, 0)_s(1, 0, 0, 12)`  
Station: `S1`  
MAE comparison vs naive: **sarima** (only claim improvement if this equals `sarima`)

| model | split | target | horizon | mae | rmse | mape | n_obs | n_mape | mape_skipped_near_zero | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sarima_o(1, 0, 0)_s(1, 0, 0, 12) | test | pm25 | 1 | 0.0000 | 0.0000 | 0.0000 | 16 | 16 | 0 | one_step_filter |
| naive_last_value_h1 | test | pm25 | 1 | 3.4250 | 3.7458 | 0.0645 | 16 | 16 | 0 | reference_baseline |
