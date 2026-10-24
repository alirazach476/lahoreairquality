# ML feature engineering

Forecasting features for Lahore air quality / AQI. **Training and inference are
out of scope** for this document — only feature construction.

| Piece | Location |
|-------|----------|
| Package | `ml/src/lahore_aqi_ml/features/` |
| Workspace / CLI | `ml/features/` |
| Tests | `tests/ml/features/` |
| Dataset output | `ml/features/datasets/` |

## Source columns (inspected)

From dbt mart ``marts.mart_air_quality_features``:

- **Keys:** `station_id`, `observed_hour`
- **AQ:** `pm25`, `pm10`, `o3`, `no2`, `so2`, `co`, `station_aqi`, `city_aqi`
- **Weather:** `temperature_c`, `relative_humidity_pct`, `wind_speed_ms`,
  `wind_direction_deg`, `pressure_hpa`, `precipitation_mm`

Mart field `pm25_rolling_24h_avg` is **not** reused as an ML feature; rollings
are recomputed causally in Python.

## Feature families

1. **Lags** (1, 2, 3, 6, 12, 24) on AQ series — value at T−k only.
2. **Rolling** mean / std / min / max over windows 3, 6, 12, 24 — backward-looking,
   includes the observation at T by default (known at end of hour T).
3. **Weather** — same-hour values (already joined on the mart).
4. **Calendar** — UTC hour, day of week, month, weekend flag from `observed_hour`.

## Leakage policy

Features at T never use rows with time &gt; T. Supervised labels are stored as
`target_{col}_lead_{h}` and listed separately from `feature_columns`.

## Missing data

Insufficient history → **NaN** (no forward-fill from the future). Early lags
and partial windows follow that rule; callers may dropna before training.

## Usage

```python
from lahore_aqi_ml.features import (
    build_feature_dataset,
    make_synthetic_mart_frame,
    save_feature_dataset,
)

frame = make_synthetic_mart_frame(n_hours=168)  # or load mart extract
dataset = build_feature_dataset(frame)
save_feature_dataset(dataset, "ml/features/datasets")
X = dataset.X
y = dataset.y("target_station_aqi_lead_1")
```
