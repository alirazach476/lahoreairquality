# ingestion/

Data collection and landing path for external air-quality and weather sources.

| Component | Role |
|-----------|------|
| `poller/` | Periodically fetch from external APIs and publish to Redpanda |
| `consumer/` | Read from Redpanda, archive raw JSON to object storage, load into Postgres |

Run both via Docker Compose from the repo root (`docker compose up -d`).  
Inspect commands: [`docs/local-stack.md`](../docs/local-stack.md).
