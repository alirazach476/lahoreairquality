# Project metrics report

**As of:** 2026-10-24 (UTC)  
**Sources:** PostgreSQL warehouse (`lahore_aqi`), FastAPI live endpoints on `localhost:8000`, ML artifacts under `ml/training/artifacts/`, and `pytest tests/resilience`.  
**Rule:** Every figure below was measured. Where a metric could not be measured from available stores, it is marked **Not available**.

Reproduce warehouse queries:

```bash
Get-Content scripts/compute_project_metrics.sql | docker exec -i lahore-aqi-postgres psql -U lahore -d lahore_aqi
# or: docker exec -i lahore-aqi-postgres psql -U lahore -d lahore_aqi < scripts/compute_project_metrics.sql
```

---

## 1. Total air-quality observations

| Metric | Value | Source |
|--------|------:|--------|
| Rows in `raw.air_quality_observations` | **841** | SQL `COUNT(*)` |
| Rows with `observed_at >= 2026-10-17` | **827** | SQL |
| Pollutant mix | pm25 **818**; temperature 7; um003 5; relativehumidity 5; pm1 5; pm10 **1** | SQL `GROUP BY pollutant` |
| Raw archive objects (`raw.ingestion_payloads`) | **1039** | SQL |

---

## 2. Total weather observations

| Metric | Value | Source |
|--------|------:|--------|
| Rows in `raw.weather_observations` | **198** | SQL `COUNT(*)` |

---

## 3. Number of Lahore sensors

| Metric | Value | Source |
|--------|------:|--------|
| Distinct `station_id` in raw AQ | **10** | SQL |
| Stations returned by `GET /api/sensors` | **9** | API `count` field |
| Stations with any observation on/after 2026-10-17 | **6** | SQL |

**Station inventory (raw AQ, by row count)**

| station_id | location_name | rows | first_obs (UTC) | last_obs (UTC) |
|------------|---------------|-----:|-----------------|----------------|
| 6125629 | ARC, Lahore | 177 | 2026-10-17 10:00 | 2026-10-24 12:00 |
| 6135353 | The University of Lahore | 168 | 2026-10-17 10:00 | 2026-10-24 11:00 |
| 6135333 | Trinity School Lahore | 161 | 2026-10-17 10:00 | 2026-10-24 10:00 |
| 6135329 | LAS Lahore | 159 | 2026-10-17 10:00 | 2026-10-24 04:00 |
| 6135351 | Hiking & Mountaineering Club GCU Lahore | 156 | 2026-10-17 10:00 | 2026-10-24 11:00 |
| 4515157 | Barki, Lahore | 8 | 2026-10-14 13:00 | 2026-10-24 12:00 |
| 1894641 | Lahore | 5 | 2024-04-24 00:54 | 2026-08-31 20:03 |
| 6509914 | DHA Phase 8 Lahore | 5 | 2026-10-01 08:00 | 2026-10-01 08:00 |
| 6135458 | Valancia Town Lahore | 1 | 2026-06-13 14:00 | 2026-06-13 14:00 |
| 8664 | US Diplomatic Post: Lahore | 1 | 2025-03-04 12:00 | 2025-03-04 12:00 |

---

## 4. Average readings per day

Computed only over **UTC calendar days that contain ≥1 observation** (not zero-filled empty days).

| Stream | Days with data | Avg rows/day | Min/day | Max/day |
|--------|---------------:|-------------:|--------:|--------:|
| Air quality | **14** | **60.07** | 1 | 118 |
| Weather | **8** | **24.75** | 24 | 30 |

---

## 5. Date range

| Stream | Min `observed_at` (UTC) | Max `observed_at` (UTC) | Span |
|--------|-------------------------|-------------------------|------|
| Air quality | **2024-04-24 00:54:24** | **2026-10-24 12:00:00** | **≈913.46 days** |
| Weather | **2026-10-17 00:00:00** | **2026-10-24 23:00:00** | **≈7.96 days** |
| AQ ingest window (`ingested_at`) | 2026-10-24 09:09:08 | 2026-10-24 12:22:13 | same calendar day (bootstrap/live load) |

Inclusive UTC calendar days from first to last AQ observation day: **914** days in `generate_series` count (many of those days have **no** rows — see completeness).

---

## 6. Data completeness

### 6.1 Citywide: distinct UTC hours with any AQ row

| Window | Present hours | Expected hours in [min,max] span | % hours with ≥1 AQ row |
|--------|--------------:|---------------------------------:|-----------------------:|
| Full AQ history | **177** | **21 925** | **0.81%** |
| Dense window `observed_at ≥ 2026-10-17` | **170** | **171** | **99.42%** |

Interpretation: the full-span percentage is depressed by sparse historical stations (2024–mid-2026). The dense recent window is nearly contiguous at city level.

### 6.2 Quality classification (measured twice — do not merge blindly)

**Live API** `GET /api/data-quality` at `evaluated_at=2026-10-24T12:55:41Z`:

| Class | AQ count | Share of 841 |
|-------|---------:|-------------:|
| valid | **25** | **2.97%** |
| suspect | **793** | **94.29%** |
| invalid | **23** | **2.73%** |
| Weather rows evaluated | **198** | — |
| Inactive stations listed | 1894641, 8664, 6135458, 6509914, 6135329 | API |

**dbt** `quality.mart_data_quality_report` (`generated_at=2026-10-24 11:47:39`):

| Field | Value |
|-------|------:|
| record_count | **831** |
| valid_count | **800** |
| suspect_count | **15** |
| invalid_count | **16** |
| duplicate_row_count | **0** |
| missing_weather_count | **14** |
| inactive_station_count | **5** |
| missing_interval_count | **6** |
| max_gap_hours | **11 186** |
| weather_record_count | **195** |
| weather_invalid_count | **11** |

Rule semantics: suspicious/invalid rows are **classified and retained**, not deleted (`docs/data-quality.md`).

---

## 7. Duplicate rate

Natural keys enforced in Postgres (`UNIQUE` on AQ and weather).

| Table | Total rows | Distinct natural keys | Duplicate natural-key rows | Duplicate `raw_record_id` rows |
|-------|-----------:|----------------------:|---------------------------:|-------------------------------:|
| `raw.air_quality_observations` | 841 | 841 | **0** | **0** |
| `raw.weather_observations` | 198 | 198 | **0** | **0** |
| dbt report `duplicate_row_count` | — | — | **0** | — |

**Duplicate rate in warehouse: 0%** (no second row for the same natural key).

---

## 8. Sensor outage / gap statistics

### PM2.5 hourly presence within each station’s own [min,max] hour span

| station_id | n_pm25 rows | Expected hours in span | Present distinct hours | % present | Missing hour slots |
|------------|------------:|-----------------------:|-----------------------:|----------:|-------------------:|
| 6125629 | 169 | 171 | 169 | **98.83%** | 2 |
| 6135353 | 168 | 170 | 168 | **98.82%** | 2 |
| 6135333 | 161 | 169 | 161 | **95.27%** | 8 |
| 6135329 | 159 | 163 | 159 | **97.55%** | 4 |
| 6135351 | 156 | 170 | 156 | **91.76%** | 14 |
| 8664 / 4515157 / 6135458 / 6509914 / 1894641 | 1 each | 1 | 1 | 100% | 0 |

Sparse stations with a single timestamp show 100% only because the span collapses to one hour — not continuous coverage.

---

## 9–12. Forecast model metrics

**Primary comparison artifact:** `ml/training/artifacts/xgboost/xgboost_metrics.md`  
**Target:** `target_pm25_lead_1` · **Horizon:** **1** (one-step) · **Split:** test  
**Training sizes (metadata):** n_train=168, n_validation=36, n_test=35 · **Features:** 196  
**Training duration:** 82.27 s (`xgboost_metadata.json`)

| Model | MAE | RMSE | MAPE (fraction) | MAPE % | n_obs |
|-------|----:|-----:|----------------:|-------:|------:|
| **xgboost_h1** | **2.8099** | **3.2844** | **0.1450** | **14.50%** | **35** |
| naive_last_value_h1 | 6.0179 | 7.0237 | 0.2573 | 25.73% | 35 |
| seasonal_naive_s24 | 3.4664 | 4.1134 | 0.1797 | 17.97% | 35 |
| sarima_reference (same eval table) | 4.1800 | 4.9832 | 0.1955 | 19.55% | 34 |

**Relative MAE (XGBoost vs baselines on this table):**

| Comparison | MAE reduction |
|------------|--------------:|
| vs naive | **53.31%** |
| vs seasonal naive (s=24) | **18.94%** |
| vs SARIMA reference | **32.78%** |

`mae_comparison.lowest_mae_among_measured` in metadata: **`xgboost_mae`**.

### Separate SARIMA training artifact

File: `ml/training/artifacts/sarima/sarima_metrics.md`  
Model: `sarima_o(1, 0, 0)_s(1, 0, 0, 12)` · target `pm25` · horizon 1 · station `S1` · test n_obs=16  

| Model | MAE | RMSE | MAPE | n_obs |
|-------|----:|-----:|-----:|------:|
| SARIMA (that artifact) | 0.0000 | 0.0000 | 0.0000 | 16 |
| naive_last_value_h1 (same artifact) | 3.4250 | 3.7458 | 0.0645 | 16 |

**Caution:** The SARIMA-only artifact’s zero-error row is **not** used as the cross-model winner. Cross-model ranking for this portfolio uses the **shared XGBoost evaluation table** above (same feature-test origins).

---

## 13. Best model

On the shared test comparison in `xgboost_metrics.md` / `xgboost_metadata.json`:

- **Best by MAE / RMSE / MAPE:** **`xgboost_h1`**
- Confirmed by metadata field `lowest_mae_among_measured = "xgboost_mae"`

---

## 14. Forecast horizon

| Item | Value |
|------|------:|
| Supervised / eval horizon | **1** (lead-1 / one-step) |
| Published `ml.forecasts` rows | **24** |
| Serving model label in demo forecasts | `xgboost` / `demo-synthetic` (seeded serving rows; not re-scored here) |

---

## 15. Average API response time

Measured 2026-10-24 locally: **5 sequential requests per endpoint** to `http://localhost:8000` via `curl` `%{time_total}` (includes local network + app + DB).

| Endpoint | Mean (ms) | Min (ms) | Max (ms) | HTTP |
|----------|----------:|---------:|---------:|------|
| `GET /health` | 18.5 | 4.4 | 26.8 | 200 |
| `GET /api/air-quality/current` | 15.4 | 7.3 | 22.4 | 200 |
| `GET /api/air-quality/history?hours=48` | 18.8 | 6.5 | 30.9 | 200 |
| `GET /api/forecast?limit=48` | 17.4 | 8.1 | 29.4 | 200 |
| `GET /api/sensors` | 17.8 | 6.1 | 40.0 | 200 |
| `GET /api/data-quality` | 71.2 | 45.7 | 105.0 | 200 |
| **Pooled (n=30)** | **26.5** | 4.4 | 105.0 | — |

Not a production load test; single-client localhost only.

---

## 16. Pipeline success / failure statistics

| Signal | Measured result |
|--------|-----------------|
| Resilience scenario catalog size | **10** (`GET /resilience/status`) |
| `pytest tests/resilience` | **27 passed**, 0 failed (run 2026-10-24) |
| Live resilience probe | `overall_healthy=true`; Postgres component healthy |
| Warehouse AQ/weather row writes under unique keys | **0** duplicate natural keys (see §7) |
| Poller success/failure counters in Postgres | **Not available** — not persisted as an aggregate table in this stack |
| Compose one-shot jobs historically | **Not available** from warehouse (no job-run ledger queried) |

---

## Mart / serving counts (context)

| Relation | Rows |
|----------|-----:|
| `marts.mart_lahore_aqi` | 174 |
| `marts.mart_air_quality_hourly` | 815 |
| `marts.mart_weather_hourly` | 192 |
| `marts.mart_air_quality_features` | 815 |
| `ml.forecasts` | 24 |

---

## CV-oriented summary (facts only)

Use these only with the caveats in this file (localhost latency; ML n_obs=35; dense vs full completeness).

1. **841** AQ + **198** weather observations loaded; **10** distinct Lahore-area stations; **0%** warehouse duplicate rate on natural keys.  
2. Dense window (≥2026-10-17): **99.42%** of hours have ≥1 AQ observation (170/171).  
3. On the shared lead-1 PM2.5 test set (**n=35**), **XGBoost MAE 2.81** vs naive **6.02** (**53.3%** lower MAE) and seasonal-naive **3.47**.  
4. Local FastAPI: pooled mean response **26.5 ms** over 30 curls; data-quality endpoint mean **71.2 ms**.  
5. **10** documented failure modes; resilience suite **27/27** tests passing at measurement time.
