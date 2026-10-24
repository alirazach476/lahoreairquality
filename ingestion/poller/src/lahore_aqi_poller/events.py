"""Ingestion events published to Redpanda as JSON."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RecordKind = Literal["air_quality", "weather"]
SourceName = Literal["openaq", "open-meteo"]


class IngestionEvent(BaseModel):
    """Normalized + raw observation envelope for the streaming pipeline.

    Idempotency: ``event_id`` equals ``idempotency_key`` and is derived from the
    source natural key (``raw_record_id``). Replays with the same key are safe.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(description="Unique event identifier (idempotent).")
    idempotency_key: str = Field(description="Stable dedupe key for consumers (same as event_id).")
    source: SourceName
    record_kind: RecordKind
    ingested_at: datetime = Field(description="UTC timestamp when the poller built this event.")
    observed_at: datetime = Field(description="UTC observation time from the source.")
    normalized: dict[str, Any]
    raw: dict[str, Any]

    @field_validator("event_id", "idempotency_key")
    @classmethod
    def require_non_blank_ids(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "event identifiers must not be blank"
            raise ValueError(msg)
        return cleaned

    def to_message_dict(self) -> dict[str, Any]:
        """JSON-serializable payload for a future Redpanda producer."""
        return self.model_dump(mode="json")
