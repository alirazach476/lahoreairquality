# Architecture (draft)

## Goal

Continuously collect Lahore air-quality and weather data, process it, calculate AQI, forecast future air quality, and expose results via API and dashboard.

## High-level flow

```text
External APIs
  → ingestion/poller → Redpanda
  → ingestion/consumer → MinIO (raw JSON) + PostgreSQL (raw)
  → dbt (staging → intermediate → marts; quality classify + report)
  → ml (features → train/infer, MLflow)
  → apps/api → apps/dashboard
```

Dagster (`orchestration/dagster`) schedules and observes these assets. It does not replace domain packages.

## Timezone

- Internal storage and computation: **UTC**
- User-facing display: **Asia/Karachi**

## Status

This document will expand as phases land. The repository currently contains structure and local infra Compose services only.
