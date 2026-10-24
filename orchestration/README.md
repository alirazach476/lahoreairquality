# orchestration/

Pipeline orchestration and scheduling.

| Component | Role |
|-----------|------|
| `dagster/` | Assets, jobs, schedules, and sensors for ingest → load → dbt → quality |

Dagster coordinates work; business logic stays in `ingestion/`, `dbt/`, and (later) `ml/`.

See [`dagster/README.md`](dagster/README.md).
