"""Validate Redpanda ingestion event envelopes (producer schema v1)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

EXPECTED_SCHEMA_NAME = "lahore_aqi.ingestion_event"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0.0"})


class SchemaMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    version: str


class IngestionEventEnvelope(BaseModel):
    """Validated consumer-side view of a poller-produced JSON event."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    schema_meta: SchemaMeta = Field(alias="schema")
    event_id: str
    idempotency_key: str
    source: Literal["openaq", "open-meteo"]
    record_kind: Literal["air_quality", "weather"]
    event_timestamp: datetime
    ingested_at: datetime
    normalized: dict[str, Any]
    raw: dict[str, Any]

    @field_validator("event_id", "idempotency_key")
    @classmethod
    def non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "identifiers must not be blank"
            raise ValueError(msg)
        return cleaned

    @model_validator(mode="after")
    def validate_schema_and_kind(self) -> IngestionEventEnvelope:
        if self.schema_meta.name != EXPECTED_SCHEMA_NAME:
            msg = (
                f"unsupported schema name {self.schema_meta.name!r}; "
                f"expected {EXPECTED_SCHEMA_NAME!r}"
            )
            raise ValueError(msg)
        if self.schema_meta.version not in SUPPORTED_SCHEMA_VERSIONS:
            msg = f"unsupported schema version {self.schema_meta.version!r}"
            raise ValueError(msg)
        if self.record_kind == "air_quality" and self.source != "openaq":
            # Allow future sources; warn only.
            logger.debug(
                "aq_source_non_openaq",
                extra={"source": self.source, "event_id": self.event_id},
            )
        return self


class EventValidationError(Exception):
    """Raised when a message cannot be decoded/validated (non-retryable)."""


def deserialize_event(payload: bytes | str | dict[str, Any]) -> IngestionEventEnvelope:
    """Parse and validate a Kafka message value.

    Raises:
        EventValidationError: malformed JSON or schema validation failure.
    """
    try:
        if isinstance(payload, dict):
            data = payload
        else:
            text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
            data = json.loads(text)
        if not isinstance(data, dict):
            raise EventValidationError("event JSON root must be an object")
        return IngestionEventEnvelope.model_validate(data)
    except EventValidationError:
        raise
    except Exception as exc:
        raise EventValidationError(f"invalid ingestion event: {exc}") from exc
