# Historical data bootstrap

Import measured Lahore air-quality history (OpenAQ v3) and model-derived weather
history (Open-Meteo archive) into the **existing** raw tables. No synthetic
observations are created.

## Command

```bash
# Plan only (default) — discovery + resource estimate, no writes
python -m ingestion.bootstrap_history --days 7

# After reviewing the plan:
python -m ingestion.bootstrap_history --execute --days 7
```

Full AQ+weather import requires: `OPENAQ_API_KEY`, reachable PostgreSQL
(migrations applied), optional MinIO/S3.

### Weather-only (no OpenAQ key)

Uses the public Open-Meteo Historical Weather API (no API key). Weather is
**model/reanalysis-derived**, not ground-station measurements. Attribution:
Open-Meteo.com (CC BY 4.0).

```bash
# Plan only — no writes
python -m ingestion.bootstrap_history --weather-only --days 7

# After reviewing the plan:
python -m ingestion.bootstrap_history --weather-only --execute --days 7
```

## Target tables (existing)

| Table | Content |
|-------|---------|
| `raw.ingestion_payloads` | Original API JSON envelopes |
| `raw.air_quality_observations` | Normalized OpenAQ measurements |
| `raw.weather_observations` | Normalized Open-Meteo hourly archive |

Object keys (when S3/MinIO is up): `raw/{kind}/{source}/YYYY/MM/DD/{event_id}.json`

## Provenance

| Stream | Provenance |
|--------|------------|
| Air quality | **Measured** OpenAQ sensor observations (PM2.5 / PM10 only when those sensors exist) |
| Weather | **Model-derived** Open-Meteo Historical Weather API at configured Lahore coordinates |

Sensor / location IDs are **discovered at runtime** — never hard-coded.

## Idempotency

Uses the same `ON CONFLICT DO NOTHING` helpers as the streaming consumer.
Reruns skip duplicates; nothing is deleted or overwritten.

## Default window

Last **7 UTC days** (`--days 7`), overridable with `--from` / `--to`.
OpenAQ fetches are chunked (`--chunk-days`, default 3) and rate-limited.

## Weather archive day boundary

Open-Meteo Historical Weather uses calendar `start_date` / `end_date` and may
return every hour of the final day. Bootstrap still **requests** that calendar
range, but **persists** only hours with `observed_at` ≤
`min(requested_window.end, current_completed_UTC_hour)`. Later hours are
skipped (not deleted). Plan output labels these separately as
`requested_window`, `weather_archive_calendar_dates`, and
`weather_persist_end_utc`. The `future_timestamp` quality rule remains enabled.
