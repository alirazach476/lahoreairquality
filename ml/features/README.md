# ml/features

Time-aware feature engineering for Lahore AQI / air-quality forecasting.

**Implementation:** `lahore_aqi_ml.features` (`ml/src/lahore_aqi_ml/features/`).  
**Do not train models here** — training lives under `ml/training/` (later).

## Inspected source columns

Built from ``marts.mart_air_quality_features`` (grain: `station_id` × `observed_hour`):

| Group | Columns |
|-------|---------|
| Keys | `station_id`, `observed_hour` |
| AQ | `pm25`, `pm10`, `o3`, `no2`, `so2`, `co`, `station_aqi`, `city_aqi` |
| Weather | `temperature_c`, `relative_humidity_pct`, `wind_speed_ms`, `wind_direction_deg`, `pressure_hpa`, `precipitation_mm` |

## Features generated

| Family | Details |
|--------|---------|
| AQ lags | 1, 2, 3, 6, 12, 24 hours |
| AQ rolling | windows 3 / 6 / 12 / 24 × mean, std, min, max (causal) |
| Weather | same-hour fields (+ optional wind sin/cos) |
| Time | hour, day of week, month, weekend indicator |
| Targets | `target_*_lead_*` labels only (not features) |

## Leakage rule

A feature at timestamp **T** may use only information available at or before **T**.
Lags use `shift(+k)` (past). Rolling windows look backward. Lead/target columns
are excluded from the feature list.

## Generate a training dataset

```bash
pip install -e "./ml[dev]"
python ml/features/generate_feature_dataset.py
# or from a mart extract:
python ml/features/generate_feature_dataset.py --from-parquet path/to/mart.parquet
```

Artifacts land in `ml/features/datasets/` (parquet + metadata JSON + FEATURES.md).

## Tests

```bash
pytest tests/ml/features -q
```
