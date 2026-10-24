# infrastructure/redpanda

Redpanda runs via the root `docker-compose.yml` (Kafka-compatible protocol).

| Topic (default) | Env var | Purpose |
|-----------------|---------|---------|
| `aq.raw` | `REDPANDA_TOPIC_AIR_QUALITY` | Air-quality ingestion events |
| `weather.raw` | `REDPANDA_TOPIC_WEATHER` | Weather ingestion events |

Topics are created by the `redpanda-init-topics` Compose service after the broker is healthy.

| Client location | Brokers |
|-----------------|---------|
| Host processes | `REDPANDA_BROKERS=localhost:19092` |
| Compose services | `redpanda:9092` |

UI: Redpanda Console at `http://localhost:8085` (see `REDPANDA_CONSOLE_PORT`).

Inspect commands: [`docs/local-stack.md`](../../docs/local-stack.md).
