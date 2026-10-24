# ingestion/consumer

Consumes Redpanda topics, archives **original** JSON to S3/MinIO, and upserts
normalized rows into PostgreSQL.

```text
Redpanda  →  Python consumer  →  S3 (raw JSON)
                              →  PostgreSQL (normalized, idempotent)
```

## Run

Via Docker Compose (preferred for local stack):

```bash
docker compose up -d consumer
docker compose logs -f consumer
```

On the host:

```bash
python -m ingestion.consumer
python -m lahore_aqi_consumer --max-messages 10
```

Requires Postgres + MinIO/S3 + Redpanda (see root `docker-compose.yml` and `docs/local-stack.md`).

## Reliability

| Stage | On failure |
|-------|------------|
| Schema validation | Reject, log, **commit** offset (non-retryable poison pill) |
| S3 put | Fail, **do not commit** — message redelivered |
| PostgreSQL upsert | Fail, **do not commit** — S3 object kept; retry is idempotent |

Order: **S3 → PostgreSQL → commit**. Partial failures are logged with
`failed_stage`, `event_id`, and `s3_key` for recovery.

S3 keys are deterministic: `raw/{kind}/{source}/{YYYY}/{MM}/{DD}/{event_id}.json`.

## Metrics

`consumed`, `processed`, `rejected`, `duplicate`, `failed`
