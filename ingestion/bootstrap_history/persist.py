"""Persist bootstrap events via existing consumer dual-write path."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from lahore_air_quality.config import Settings, get_settings
from lahore_aqi_consumer.processing import EventProcessor, ProcessResult
from lahore_aqi_consumer.storage.postgres import PostgresObservationWriter
from lahore_aqi_consumer.storage.s3 import S3ObjectStore
from lahore_aqi_poller.events import IngestionEvent
from lahore_aqi_poller.producers.serialization import serialize_event

logger = logging.getLogger(__name__)


@dataclass
class PersistStats:
    attempted: int = 0
    processed: int = 0
    duplicates: int = 0
    rejected: int = 0
    failed: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    def record(self, result: ProcessResult) -> None:
        self.attempted += 1
        if result.status == "processed":
            self.processed += 1
        elif result.status == "duplicate":
            self.duplicates += 1
        elif result.status == "rejected":
            self.rejected += 1
        else:
            self.failed += 1
            self.failures.append(
                {
                    "event_id": result.event_id,
                    "detail": result.detail,
                    "failed_stage": result.failed_stage,
                }
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "processed": self.processed,
            "duplicates": self.duplicates,
            "rejected": self.rejected,
            "failed": self.failed,
            "failures_sample": self.failures[:20],
        }


class NullObjectStore:
    """No-op object store when MinIO/S3 is unavailable (Postgres-only bootstrap)."""

    def put_json(self, *, key: str, document: dict[str, Any]) -> Any:
        from lahore_aqi_consumer.storage.s3 import ObjectPutResult

        return ObjectPutResult(bucket="none", key=key, already_existed=False)

    def exists(self, *, key: str) -> bool:
        return False


def build_event_processor(
    session_factory: Callable[[], Session],
    *,
    settings: Settings | None = None,
    require_object_store: bool = False,
) -> tuple[EventProcessor, str]:
    """Build processor reusing consumer Postgres writer + optional S3."""
    cfg = settings or get_settings()
    postgres = PostgresObservationWriter(session_factory)
    storage_mode = "postgres+s3"
    try:
        store: Any = S3ObjectStore(
            endpoint_url=cfg.s3_endpoint_url,
            bucket=cfg.s3_bucket,
            access_key_id=cfg.aws_access_key_id.get_secret_value(),
            secret_access_key=cfg.aws_secret_access_key.get_secret_value(),
            region=cfg.aws_region,
        )
        # Lightweight connectivity probe — if it fails, fall back unless required.
        try:
            store.exists(key="raw/_bootstrap_probe")
        except Exception as exc:  # noqa: BLE001
            if require_object_store:
                raise
            logger.warning(
                "object_store_unavailable_falling_back_to_postgres_only",
                extra={"error_type": type(exc).__name__},
            )
            store = NullObjectStore()
            storage_mode = "postgres_only"
    except Exception as exc:  # noqa: BLE001
        if require_object_store:
            raise
        logger.warning(
            "object_store_init_failed_postgres_only",
            extra={"error_type": type(exc).__name__},
        )
        store = NullObjectStore()
        storage_mode = "postgres_only"

    return EventProcessor(object_store=store, postgres_writer=postgres), storage_mode


def persist_event(processor: EventProcessor, event: IngestionEvent, stats: PersistStats) -> None:
    payload = serialize_event(event)
    result = processor.process(payload)
    stats.record(result)
