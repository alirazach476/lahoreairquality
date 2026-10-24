# orchestration/dagster

Dagster orchestration for Lahore AQI (ingest → load → dbt → quality). **No ML.**

## Pipeline

```text
raw_events_published          # OpenAQ / Open-Meteo → Redpanda
        ↓
raw_observations_loaded       # Redpanda → MinIO + PostgreSQL (bounded drain)
        ↓
dbt_models                    # dbt seed + run
        ↓
data_quality_checks           # dbt test (+ soft source freshness)
```

## Failure kinds

| Kind | Retry? | Examples |
|------|--------|----------|
| `temporary_api_failure` | yes | OpenAQ/Open-Meteo transient, rate limit, Redpanda/S3 blip |
| `data_validation_failure` | no | OpenAQ auth / invalid credentials |
| `database_failure` | yes | Postgres down, write errors |
| `transformation_failure` | no | dbt seed/run/test non-zero |

Metadata is attached to Dagster `Failure` for UI / monitoring.

## Jobs

| Job | Stages |
|-----|--------|
| `ingest_and_load_job` | poll + consume/load |
| `dbt_only_job` | dbt + quality |
| `full_pipeline_job` | all assets |

Schedules/sensors default to **STOPPED**. They skip ticks when the same job is already active (no duplicate stacking).

## Local development

```bash
# From repo root — install app packages + Dagster
pip install -e ".[orchestration]"
pip install -e ingestion/poller -e ingestion/consumer -e orchestration/dagster

# Ensure .env exists (Postgres/Redpanda/MinIO secrets)
cp -n .env.example .env

# Optional: start infra
docker compose up -d postgres minio minio-init redpanda redpanda-init-topics migrate

# Launch UI (DAGSTER_HOME = this directory so dagster.yaml applies)
make dagster-dev
# or:
cd orchestration/dagster
# PowerShell: $env:DAGSTER_HOME = (Get-Location).Path
export DAGSTER_HOME="$(pwd)"
dagster dev -w workspace.yaml
```

Open http://localhost:3000 — materialize `full_pipeline_job` or individual assets.

### Env knobs (non-secret)

| Variable | Purpose |
|----------|---------|
| `DAGSTER_CONSUMER_MAX_MESSAGES` | Bounded consume batch (default 200) |
| `DAGSTER_INGEST_CRON` | Override ingest schedule cron |
| `DAGSTER_FULL_PIPELINE_CRON` | Override full pipeline cron (default hourly) |
| `DBT_PROFILES_DIR` / `DBT_PROJECT_DIR` | dbt paths |
| `POLL_INTERVAL_SECONDS` | Influences default ingest cron |

Secrets (`POSTGRES_*`, `OPENAQ_API_KEY`, `AWS_*`, …) stay in `.env` / the environment.

## Independent stage tests

Stage functions under `lahore_aqi_dagster.stages` are plain callables — unit-tested without the Dagster daemon:

```bash
pytest tests/orchestration -v
```
