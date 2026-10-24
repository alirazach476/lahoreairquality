# infrastructure/docker

Dockerfiles for the local Compose stack.

| Path | Image / use |
|------|-------------|
| `postgres/` | `lahore-aqi-postgres:16` |
| `poller/` | `lahore-aqi-poller:local` — OpenAQ/Open-Meteo → Redpanda |
| `consumer/` | `lahore-aqi-consumer:local` — Redpanda → MinIO + Postgres; also runs Alembic (`migrate` service) |

Core orchestration lives in the root [`docker-compose.yml`](../../docker-compose.yml).  
Operator inspect commands: [`docs/local-stack.md`](../../docs/local-stack.md).

Not in Compose yet: Dagster, dbt, MLflow, FastAPI, React.
