"""JSON serialization for Redpanda ingestion events."""

from __future__ import annotations

import json
from typing import Any, Final

from lahore_aqi_poller.events import IngestionEvent

SCHEMA_NAME: Final[str] = "lahore_aqi.ingestion_event"
SCHEMA_VERSION: Final[str] = "1.0.0"


def build_event_envelope(event: IngestionEvent) -> dict[str, Any]:
    """Build the Kafka message body with schema metadata and required fields."""
    return {
        "schema": {
            "name": SCHEMA_NAME,
            "version": SCHEMA_VERSION,
        },
        "event_id": event.event_id,
        "idempotency_key": event.idempotency_key,
        "source": event.source,
        "record_kind": event.record_kind,
        # Domain event time (observation) + pipeline ingestion time.
        "event_timestamp": event.observed_at.isoformat(),
        "ingested_at": event.ingested_at.isoformat(),
        "normalized": event.normalized,
        "raw": event.raw,
    }


def serialize_event(event: IngestionEvent) -> bytes:
    """Serialize an ingestion event to UTF-8 JSON bytes."""
    return json.dumps(
        build_event_envelope(event),
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
