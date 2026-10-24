"""Append-friendly raw ingestion payload storage.

Duplicate source records are handled with ``ON CONFLICT DO NOTHING`` — rows are
never deleted when a replay arrives.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from lahore_air_quality.db.base import Base


class RecordKind(enum.StrEnum):
    """Discriminator for the domain of a raw payload."""

    AIR_QUALITY = "air_quality"
    WEATHER = "weather"


class IngestionPayload(Base):
    """Immutable-ish raw JSON payload landed from an upstream source.

    Natural idempotency key: ``(source, raw_record_id)``.
    """

    __tablename__ = "ingestion_payloads"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "raw_record_id",
            name="uq_ingestion_payloads_source_raw_record_id",
        ),
        Index("ix_ingestion_payloads_ingested_at", "ingested_at"),
        Index("ix_ingestion_payloads_kind_ingested_at", "record_kind", "ingested_at"),
        {"schema": "raw"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    record_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_record_id: Mapped[str] = mapped_column(String(256), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
