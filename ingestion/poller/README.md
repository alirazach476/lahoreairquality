# ingestion/poller

Periodically polls OpenAQ (air quality) and Open-Meteo (weather) for Lahore,
then publishes JSON events to Redpanda (Kafka protocol).

## Run

Via Docker Compose (preferred for local stack):

```bash
docker compose up -d poller
docker compose logs -f poller
```

On the host (requires Redpanda from Compose):

```bash
python -m ingestion.poller
python -m ingestion.poller --once
python -m lahore_aqi_poller --interval 60
python -m ingestion.poller --no-redpanda --once   # dry-run (no broker)
```

| Variable | Default | Meaning |
|----------|---------|---------|
| `POLL_INTERVAL_SECONDS` | `300` | Seconds between cycles |
| `POLL_ONCE` | `false` | Single cycle then exit |
| `POLL_ENABLE_OPENAQ` | `true` | Enable OpenAQ polls |
| `POLL_ENABLE_OPENMETEO` | `true` | Enable Open-Meteo polls |
| `REDPANDA_BROKERS` | `localhost:19092` | Kafka bootstrap servers |
| `REDPANDA_TOPIC_AIR_QUALITY` | `aq.raw` | AQ events topic |
| `REDPANDA_TOPIC_WEATHER` | `weather.raw` | Weather events topic |
| `OPENAQ_API_KEY` | _(empty)_ | Required for OpenAQ |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `true` | Structured logging |

## Redpanda producer

- Library: `confluent-kafka` (Kafka-compatible)
- `acks=all`, `enable.idempotence=true`
- Message key = stable `event_id` (idempotency key)
- JSON envelope includes schema name/version, source, `event_timestamp`, `ingested_at`
- Health check via cluster metadata (`RedpandaPublisher.health_check()`)

Does **not** write to PostgreSQL — that is the consumer’s job.
