# Failure simulations and recovery

Portfolio / interview section: how the Lahore AQI pipeline behaves when real
dependencies fail — detection, logging, retry, no silent data loss, recovery,
and operator-visible status.

Machine-readable contracts: `lahore_air_quality.resilience.scenarios`  
Executable simulations: `tests/resilience/test_failure_scenarios.py`  
HTTP catalog: `GET /resilience/scenarios`, live probe: `GET /resilience/status`

```bash
pytest tests/resilience -v
# or: make test-resilience
```

---

## Design principles

| Principle | How we enforce it |
|-----------|-------------------|
| **Detect** | Typed errors, health probes, quality rules, metrics counters |
| **Log** | Structured events (`poll_failed`, `processing_failed`, `event_rejected`, …) with `event_id` / stage |
| **Retry when appropriate** | HTTP backoff; Kafka producer retries; consumer exponential backoff **without** committing offsets |
| **No silent data loss** | No fabricated observations; dual-write order S3→Postgres; rejects are explicit |
| **Recover** | Next poll cycle / Kafka redelivery / freshness clears when data resumes |
| **Expose status** | Metrics, quality report, `GET /health`, `/resilience/*` |

There is **no dead-letter topic** today. Non-retryable poison messages are
**rejected + offset committed** (with logs and, when applicable, S3 audit
objects). Retryable sink failures **hold the offset**.

---

## Scenario matrix

### 1. OpenAQ unavailable

| Step | Behavior |
|------|----------|
| Detect | `OpenAQError` after client retries (or client missing) |
| Log | `poll_failed` / `openaq_client_unavailable` |
| Retry | Up to 3 HTTP attempts + backoff; **next poll cycle** retries the provider |
| Loss | No AQ rows invented; **Open-Meteo continues** in the same cycle |
| Recover | Successful fetch publishes normally |
| Status | `PollMetrics.failed_polls`; scenario id `openaq_unavailable` |

### 2. Open-Meteo unavailable

Symmetric to OpenAQ: weather leg fails independently; AQ still publishes.
Logs `poll_failed`; recovers on the next successful `fetch_current()`.

### 3. Redpanda unavailable

| Step | Behavior |
|------|----------|
| Detect | `ProducerHealth.healthy=False`; `RedpandaPublishError`; consumer `kafka_message_error` |
| Log | `publish_failed`, `redpanda_health_degraded`, `kafka_message_error` |
| Retry | Producer `retries=8` + idempotence; failed poll publishes count as **rejected** for that cycle (re-fetched next poll). Consumer **does not commit** on broker errors |
| Loss | Unpublished events never hit Postgres/MinIO |
| Recover | Health probe OK → publish/consume resumes |
| Status | `ProducerHealth`; `ConsumerMetrics.failed` |

### 4. PostgreSQL unavailable

| Step | Behavior |
|------|----------|
| Detect | `PostgresWriteError`; `check_database_health()`; API `GET /health` → **503** |
| Log | `processing_failed` (`failed_stage=postgres`), `offset_not_committed` |
| Retry | Consumer backoff 2s→60s; **offset held**; S3 object already written |
| Loss | Message remains on the topic until PG accepts the write |
| Recover | Redelivery → idempotent upsert → commit |
| Status | `/health` `database=down`; `/resilience/status` |

### 5. Object storage unavailable

S3/MinIO is attempted **before** Postgres. On `ObjectStoreError`:

- Log `processing_failed` with `failed_stage=s3`
- **Do not** write Postgres (prevents warehouse rows without a raw archive)
- Do not commit Kafka offset; backoff and retry
- When MinIO returns: deterministic key PUT + PG write + commit

### 6. Malformed event

| Kind | Outcome |
|------|---------|
| Invalid envelope / JSON | `rejected` at validate; **no S3/PG**; commit offset (avoid poison loop) |
| Valid envelope, bad normalized shape | `PermanentPostgresWriteError` → `rejected` at `postgres_validate`; S3 may already hold the payload for audit; commit offset |
| Poller transform failure | Event dropped from publish; `records_rejected` |

Never turns bad JSON into fake sensor readings.

### 7. Duplicate event

Stable `event_id` / `idempotency_key` + Postgres `ON CONFLICT DO NOTHING` +
deterministic S3 keys. Second delivery → `ProcessResult.status=duplicate`,
offset committed, **row counts unchanged**.

### 8. Stale sensor

Observability (not ingestion drop):

- `is_stale` when latest `observed_at` older than `STALE_AFTER` (12h)
- `inactive_stations` after `SENSOR_INACTIVE_AFTER` (6h)
- API freshness on current AQI responses

When new observations arrive, the quality report / API freshness recover.

### 9. Missing readings

- Empty provider response → `poll_empty_result` (success with zero publishes)
- `rule_missing_value` / `rule_missing_timestamp` → invalid classification
- `find_missing_intervals` reports gaps; **never imputes zeros**

### 10. Delayed event

`ingested_at − observed_at > DELAYED_INGEST_AFTER` (6h) → `delayed_ingest`
(**suspect**, retained). Report exposes `delayed_ingest_count` and
`max_ingest_delay_hours`. Late/backfill data is welcome; delay is visible.

---

## Interview talking points

1. **Partial failure isolation** — OpenAQ down does not stop Open-Meteo (and vice versa).
2. **At-least-once + idempotent sinks** — Kafka redelivery is safe because of conflict keys and deterministic object keys.
3. **S3-before-PG** — Prefer temporary warehouse lag over orphan DB rows without an archive.
4. **Reject vs retry** — Schema poison pills commit; infrastructure failures do not.
5. **Observability over deletion** — Stale, missing, and delayed data are classified and reported, not silently rewritten.

---

## Related docs

- [`data-quality.md`](data-quality.md) — rule definitions
- [`testing.md`](testing.md) — how to run suites
- [`local-stack.md`](local-stack.md) — Compose dependencies used in smoke tests
