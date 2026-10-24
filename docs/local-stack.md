# Local development stack

Docker Compose runs the full application stack: PostgreSQL, MinIO (object storage),
Redpanda, ingestion poller + consumer, MLflow, Dagster (webserver + daemon),
FastAPI, and the React dashboard.

## Prerequisites

- Docker Engine + Compose v2
- Copy env template once:

```bash
cp .env.example .env
# Set OPENAQ_API_KEY if you want live air-quality polls
```

Secrets come from `.env` only — they are not hard-coded in Compose files.

Host-side tools keep `localhost` addresses in `.env`. Containers override service
discovery (`postgres`, `redpanda:9092`, `http://minio:9000`, `http://mlflow:5000`)
via Compose `environment`.

## Start / stop / logs

```bash
docker compose up -d --build
# or: make compose-up

docker compose down
# or: make compose-down

docker compose logs -f
# or: make compose-logs          # app services only

docker compose ps
# or: make compose-ps
```

Optional Redpanda Console (not required by the app):

```bash
docker compose --profile devtools up -d redpanda-console
```

Production-lean port binding (infra ports not published):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Wipe all persistent data:

```bash
docker compose down -v
```

## Service map

| Service | Role | Host access |
|---------|------|-------------|
| `postgres` | Warehouse | `localhost:5432` |
| `minio` | S3-compatible archive (Adobe S3Mock locally) | API `localhost:9000` (maps to container `:9090`) |
| `minio-init` | Readiness marker after object store is up | (one-shot) |
| `redpanda` | Kafka-compatible broker | Kafka `localhost:19092` |
| `redpanda-init-topics` | Creates `aq.raw` / `weather.raw` | (one-shot) |
| `redpanda-console` | Topic UI (`devtools` profile) | `http://localhost:8085` |
| `migrate` | `alembic upgrade head` | (one-shot) |
| `poller` | OpenAQ + Open-Meteo → Redpanda | logs |
| `consumer` | Redpanda → MinIO + Postgres | logs |
| `mlflow` | Experiment tracking | `http://localhost:5000` |
| `dagster-webserver` | Orchestration UI | `http://localhost:3000` |
| `dagster-daemon` | Schedules / run queue | logs |
| `api` | FastAPI | `http://localhost:8000` · docs `/docs` |
| `dashboard` | React (nginx) | `http://localhost:8080` |

Persistent volumes: `postgres_data`, `minio_data`, `redpanda_data`, `dagster_home`,
`mlflow_data`, `mlflow_artifacts`, `ml_artifacts`, `ml_features`.

App images run as non-root (`uid 10001`) where practical. Health checks gate
`depends_on` for Postgres, Redpanda, API, dashboard, Dagster webserver, and MLflow.

## Tests

```bash
# Inside Compose (uses CI Postgres; excludes live APIs + smoke)
docker compose --profile tools run --rm test
# or: make compose-test

# On the host (stack may already be up)
make test
# or: pytest -m "not integration and not smoke"

# Live external APIs (opt-in; not part of normal Compose up)
RUN_EXTERNAL_API_TESTS=1 make test-integration

# End-to-end ingestion smoke (mocked OpenAQ/Open-Meteo)
make smoke
```

## dbt

```bash
# Against Compose Postgres (container network)
docker compose --profile tools run --rm dbt \
  sh -c "dbt deps && dbt seed --target dev && dbt run --target dev"
# or: make compose-dbt

docker compose --profile tools run --rm dbt dbt test --target dev
# or: make compose-dbt-test

# On the host (POSTGRES_HOST=localhost from .env)
make dbt-deps && make dbt-run && make dbt-test
```

## Training (XGBoost → MLflow)

```bash
# Synthetic demo (no warehouse features required)
docker compose --profile tools run --rm train
# or: make compose-train-synthetic

# From a feature parquet under the ml_features volume / image path
docker compose --profile tools run --rm train \
  python ml/training/train_xgboost.py \
  --from-features ml/features/datasets/lahore_aqi_features.parquet \
  -v
# or: make compose-train
```

Artifacts land in the `ml_artifacts` volume (also mounted into the API for forecasts).
MLflow UI: [http://localhost:5000](http://localhost:5000).

## Inspect PostgreSQL

```bash
docker compose exec postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

docker compose run --rm migrate alembic current
```

## Inspect Redpanda

```bash
docker compose exec redpanda rpk cluster health
docker compose exec redpanda rpk topic list --brokers redpanda:9092
```

## Inspect MinIO

Web console: [http://localhost:9001](http://localhost:9001)  
(login with `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` from `.env`)

## Dev vs production Compose

| Concern | Default `docker-compose.yml` | `docker-compose.prod.yml` overlay |
|---------|------------------------------|-----------------------------------|
| Audience | Local developers | Shared/staging hosts |
| Infra ports | Published (Postgres, MinIO, Redpanda) | Not published |
| Restart | `unless-stopped` | `always` |
| Images | Same multi-stage, non-root app images | Same |
| Deploy | Not included | Not included |

Dashboard `VITE_API_BASE_URL` is a **build-time** argument (browser must reach the API URL).
Rebuild the dashboard image after changing it:

```bash
docker compose build --build-arg VITE_API_BASE_URL=http://localhost:8000 dashboard
docker compose up -d dashboard
```
