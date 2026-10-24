# Data model — persistence layer

## Schemas

| Schema | Role |
|--------|------|
| `raw` | Ingestion landing: raw JSON payloads + normalized observations |
| `staging` / `intermediate` / `marts` / `quality` | Owned by dbt (`dbt/lahore_air_quality`) |
| `seeds` | dbt seed tables (AQI breakpoints, pollutant aliases) |
| `ml` | Reserved for ML artifacts (later phase) |

## Tables (`raw`)

### `ingestion_payloads`

Append-friendly archive of source JSON. **Never deleted** on duplicate replays.

- Unique: `(source, raw_record_id)`
- Idempotent insert: `ON CONFLICT DO NOTHING`

### `air_quality_observations`

Normalized pollutant readings.

| Field | Notes |
|-------|--------|
| `observation_id` | Upstream ID when available |
| `station_id` | Sensor/station identifier |
| location fields | `location_name`, `latitude`, `longitude` |
| `pollutant`, `value`, `unit` | Measurement |
| `observed_at` | Event time (UTC) |
| `ingested_at` | Load time (UTC) |
| `source`, `raw_record_id` | Provenance |

- Unique / idempotency: `(source, station_id, pollutant, observed_at)`
- Indexes: B-tree on time/station/pollutant; **BRIN** on `observed_at` for scale

### `weather_observations`

| Field | Notes |
|-------|--------|
| `observed_at`, `latitude`, `longitude` | Spatiotemporal key |
| weather metrics | temp, humidity, precip, wind, pressure |
| `source`, `raw_record_id`, `ingested_at` | Provenance |

- Unique / idempotency: `(source, latitude, longitude, observed_at)`
- BRIN on `observed_at`

## dbt lineage (analytics)

```text
raw.*
  → staging.staging_air_quality / staging_weather
  → intermediate (dedupe, timestamps, pollutant/weather rules, AQI, join)
  → marts.mart_air_quality_hourly
       marts.mart_weather_hourly
       marts.mart_lahore_aqi
       marts.mart_air_quality_features
  → quality.int_*_classified
       quality.mart_data_quality_report   (classify only — never deletes)
```

Quality rules: [`data-quality.md`](data-quality.md).  
See [`dbt/lahore_air_quality/README.md`](../dbt/lahore_air_quality/README.md).

## Scaling notes

- Append-only raw + normalized design; duplicates skip inserts without deletes.
- BRIN indexes favour large chronological tables.
- Future: `PARTITION BY RANGE (observed_at)` if a single partition grows unwieldy.
