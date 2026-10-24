# dbt / lahore_air_quality

PostgreSQL dbt project for Lahore air-quality transforms.

```text
raw → staging → intermediate → marts
              ↘ quality (classify + report; never deletes)
```

ML training is **out of scope** here (`mart_air_quality_features` only prepares a feature table).

AQI methodology (US EPA / AirNow): [`docs/aqi.md`](../../docs/aqi.md).  
Pure Python calculator (unit-tested): `lahore_air_quality.aqi`.  
Data quality rules: [`docs/data-quality.md`](../../docs/data-quality.md) / `lahore_air_quality.quality`.

## Lineage

| Layer | Models | Role |
|-------|--------|------|
| **raw** (source) | `air_quality_observations`, `weather_observations` | Owned by the ingestion consumer |
| **staging** | `staging_air_quality`, `staging_weather` | Rename / cast only |
| **intermediate** | dedupe → timestamps → pollutant/weather normalize → AQI sub-index → AQ×weather join | Business transforms |
| **marts** | `mart_air_quality_hourly`, `mart_weather_hourly`, `mart_lahore_aqi`, `mart_air_quality_features` | Analytics grains (incremental) |
| **quality** | `int_air_quality_classified`, `int_weather_classified`, `mart_data_quality_report` | valid/suspect/invalid + observability |

Business rules for AQI breakpoints and pollutant aliases live in **seeds** and **macros**, not scattered across mart SQL.

## Prerequisites

1. PostgreSQL with `raw` tables migrated (`alembic upgrade head` or Compose `migrate`).
2. Environment credentials (same as the app `.env`):
   - `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
3. dbt Postgres adapter:

   ```bash
   pip install "dbt-postgres>=1.7,<2.0"
   ```

## Run

From the repo root:

```bash
export DBT_PROFILES_DIR="$(pwd)/dbt/lahore_air_quality"   # PowerShell: $env:DBT_PROFILES_DIR = "..."
cd dbt/lahore_air_quality

dbt deps
dbt seed
dbt run
dbt test
dbt source freshness
```

Or via Make from the repo root:

```bash
make dbt-deps
make dbt-run
make dbt-test
```

## Intermediate models

| Model | Concern |
|-------|---------|
| `int_air_quality_deduplicated` / `int_weather_deduplicated` | Latest ingest wins |
| `int_*_timestamps_normalized` | UTC + `observed_hour` |
| `int_air_quality_pollutants_normalized` | Canonical codes, units, validity flags |
| `int_weather_metrics_normalized` | Physical ranges |
| `int_air_quality_aqi_subindex` | EPA sub-index via `aqi_breakpoints` seed |
| `int_air_quality_weather_joined` | Same-hour nearest weather |

## Marts

| Model | Grain | Materialization |
|-------|-------|-----------------|
| `mart_air_quality_hourly` | station × pollutant × hour | incremental merge |
| `mart_weather_hourly` | lat/lon × hour | incremental merge |
| `mart_lahore_aqi` | city × hour | incremental merge |
| `mart_air_quality_features` | station × hour (wide) | incremental merge |

## Quality

| Model | Role |
|-------|------|
| `int_air_quality_classified` / `int_weather_classified` | Per-row `quality_class` + flags (rows retained) |
| `mart_data_quality_report` | Counts, duplicates, nulls, freshness, sensors, min/max, gaps |

```bash
dbt run --select path:models/quality
dbt test --select path:models/quality
```

## Tests

- Column: `not_null`, `unique`, `accepted_values`, `relationships`, `dbt_utils.accepted_range`, `unique_combination_of_columns`
- Quality: `expression_is_true` per rule → class; singular `assert_no_auto_delete_classified`
- Source: freshness on `ingested_at`
- Singular: no invalid pollutants in marts; AQI in 0–500; nonnegative feature concentrations

## Docs

```bash
dbt docs generate
dbt docs serve
```
