# Baseline evaluation

Source: `synthetic:make_synthetic_mart_frame`

| model | split | target | horizon | mae | rmse | mape | n_obs | n_mape | mape_skipped_near_zero | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| naive_last_value_h1 | train | pm25 | 1 | 5.8710 | 7.0313 | 0.1938 | 334 | 334 | 0 |  |
| seasonal_naive_s24 | train | pm25 | 1 | 3.3324 | 4.2218 | 0.1165 | 288 | 288 | 0 | season=24 |
| naive_last_value_h1 | validation | pm25 | 1 | 5.7015 | 6.8314 | 0.1443 | 72 | 72 | 0 |  |
| seasonal_naive_s24 | validation | pm25 | 1 | 3.4354 | 4.2609 | 0.0904 | 72 | 72 | 0 | season=24 |
| naive_last_value_h1 | test | pm25 | 1 | 5.3064 | 6.6210 | 0.1860 | 72 | 72 | 0 |  |
| seasonal_naive_s24 | test | pm25 | 1 | 3.3442 | 4.1840 | 0.1241 | 72 | 72 | 0 | season=24 |
