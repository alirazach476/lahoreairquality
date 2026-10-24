"""Core event processing: validate → S3 → PostgreSQL.

Ordering and recovery
---------------------
1. Validate envelope (non-retryable reject on failure).
2. Archive **original** JSON to S3 at a deterministic key.
3. Upsert normalized rows into PostgreSQL (idempotent).
4. Caller commits the Kafka offset **only** after this method returns success.

If S3 fails, PostgreSQL is not attempted and the offset is not committed — the
message is retried. If S3 succeeds and PostgreSQL fails, the offset is not
committed; retry re-PUTs the same S3 object (same key) and retries PG. Failures
are logged with ``event_id``, ``s3_key``, and ``failed_stage`` for recovery.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from lahore_aqi_consumer.schema import (
    EventValidationError,
    IngestionEventEnvelope,
    deserialize_event,
)
from lahore_aqi_consumer.storage.postgres import (
    PermanentPostgresWriteError,
    PostgresObservationWriter,
    PostgresWriteError,
)
from lahore_aqi_consumer.storage.s3 import (
    ObjectStore,
    ObjectStoreError,
    build_raw_object_key,
)

logger = logging.getLogger(__name__)

ProcessStatus = Literal["processed", "duplicate", "rejected", "failed"]


@dataclass(frozen=True, slots=True)
class ProcessResult:
    status: ProcessStatus
    event_id: str | None = None
    source: str = "unknown"
    s3_key: str | None = None
    failed_stage: str | None = None
    detail: str | None = None
    # Which sinks completed before failure (for operators / recovery).
    s3_ok: bool = False
    postgres_ok: bool = False


class EventProcessor:
    """Process one Kafka message payload end-to-end."""

    def __init__(
        self,
        *,
        object_store: ObjectStore,
        postgres_writer: PostgresObservationWriter,
    ) -> None:
        self._store = object_store
        self._postgres = postgres_writer

    def process(self, payload: bytes | str | dict[str, Any]) -> ProcessResult:
        """Validate and dual-write. Raises nothing for reject; raises for retryables?

        Returns ``failed`` for retryable sink errors without raising, so the
        consumer loop can avoid committing offsets while keeping control flow
        simple. Callers must **not** commit on ``failed``.
        """
        try:
            envelope = deserialize_event(payload)
        except EventValidationError as exc:
            logger.error(
                "event_rejected",
                extra={"reason": str(exc), "failed_stage": "validate"},
            )
            return ProcessResult(
                status="rejected",
                detail=str(exc),
                failed_stage="validate",
            )

        original_document = _original_document(payload, envelope)
        s3_key = build_raw_object_key(
            record_kind=envelope.record_kind,
            source=envelope.source,
            event_id=envelope.event_id,
            event_timestamp=envelope.event_timestamp,
        )

        # --- Stage: S3 ---
        try:
            put_result = self._store.put_json(key=s3_key, document=original_document)
        except ObjectStoreError as exc:
            logger.error(
                "processing_failed",
                extra={
                    "event_id": envelope.event_id,
                    "failed_stage": "s3",
                    "s3_key": s3_key,
                    "s3_ok": False,
                    "postgres_ok": False,
                    "error": str(exc),
                },
            )
            return ProcessResult(
                status="failed",
                event_id=envelope.event_id,
                source=envelope.source,
                s3_key=s3_key,
                failed_stage="s3",
                detail=str(exc),
                s3_ok=False,
                postgres_ok=False,
            )

        # --- Stage: PostgreSQL ---
        try:
            pg_result = self._postgres.write(envelope)
        except PermanentPostgresWriteError as exc:
            # Poison normalized payload: archive already in S3; reject + allow commit.
            logger.error(
                "event_rejected",
                extra={
                    "event_id": envelope.event_id,
                    "failed_stage": "postgres_validate",
                    "s3_key": s3_key,
                    "s3_ok": True,
                    "postgres_ok": False,
                    "error": str(exc),
                    "recovery": (
                        "Non-retryable normalized shape; S3 retained for audit; "
                        "Kafka offset may be committed to avoid infinite retries"
                    ),
                },
            )
            return ProcessResult(
                status="rejected",
                event_id=envelope.event_id,
                source=envelope.source,
                s3_key=s3_key,
                failed_stage="postgres_validate",
                detail=str(exc),
                s3_ok=True,
                postgres_ok=False,
            )
        except PostgresWriteError as exc:
            logger.error(
                "processing_failed",
                extra={
                    "event_id": envelope.event_id,
                    "failed_stage": "postgres",
                    "s3_key": s3_key,
                    "s3_ok": True,
                    "postgres_ok": False,
                    "error": str(exc),
                    "recovery": (
                        "S3 object retained; Kafka offset not committed — "
                        "redelivery will retry PostgreSQL idempotently"
                    ),
                },
            )
            return ProcessResult(
                status="failed",
                event_id=envelope.event_id,
                source=envelope.source,
                s3_key=s3_key,
                failed_stage="postgres",
                detail=str(exc),
                s3_ok=True,
                postgres_ok=False,
            )

        if pg_result.is_duplicate and put_result.already_existed:
            status: ProcessStatus = "duplicate"
        else:
            status = "processed"

        logger.info(
            "processing_ok",
            extra={
                "event_id": envelope.event_id,
                "source": envelope.source,
                "record_kind": envelope.record_kind,
                "s3_key": s3_key,
                "status": status,
                "s3_ok": True,
                "postgres_ok": True,
            },
        )
        return ProcessResult(
            status=status,
            event_id=envelope.event_id,
            source=envelope.source,
            s3_key=s3_key,
            s3_ok=True,
            postgres_ok=True,
        )


def _original_document(
    payload: bytes | str | dict[str, Any],
    envelope: IngestionEventEnvelope,
) -> dict[str, Any]:
    """Prefer the exact decoded JSON object; fall back to model dump."""
    if isinstance(payload, dict):
        return dict(payload)
    try:
        import json

        raw = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:  # noqa: BLE001
        logger.warning(
            "original_json_reparse_failed",
            extra={"event_id": envelope.event_id},
        )
    return envelope.model_dump(mode="json", by_alias=True)
