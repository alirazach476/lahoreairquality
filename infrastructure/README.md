# infrastructure/

Local and deployable infrastructure helpers.

| Path | Purpose |
|------|---------|
| `docker/` | Dockerfiles for Postgres, poller, and consumer |
| `postgres/` | Database init scripts and schema bootstrap |
| `redpanda/` | Topic naming notes for the Kafka-compatible broker |

Start the stack from the repo root:

```bash
cp .env.example .env
docker compose up -d
```

See [`docs/local-stack.md`](../docs/local-stack.md) for inspection commands.
