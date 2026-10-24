"""Normalized air-quality observations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from lahore_air_quality.db.base import Base


class AirQualityObservation(Base):
    """One pollutant measurement at a station/sensor and observation time.

    Idempotency key: ``(source, station_id, pollutant, observed_at)``.
    Raw payloads are stored separately in ``raw.ingestion_payloads`` and are
    never deleted when a duplicate observation arrives.
    """

    __tablename__ = "air_quality_observations"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "station_id",
            "pollutant",
            "observed_at",
            name="uq_aq_obs_source_station_pollutant_observed_at",
        ),
        Index("ix_aq_obs_observed_at", "observed_at"),
        Index("ix_aq_obs_station_observed_at", "station_id", "observed_at"),
        Index("ix_aq_obs_pollutant_observed_at", "pollutant", "observed_at"),
        Index("ix_aq_obs_ingested_at", "ingested_at"),
        Index("ix_aq_obs_raw_record_id", "raw_record_id"),
        {"schema": "raw"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    observation_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Upstream observation identifier when the source provides one.",
    )
    station_id: Mapped[str] = mapped_column(String(128), nullable=False)
    location_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    pollutant: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_record_id: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        doc="Links to raw.ingestion_payloads.raw_record_id for the same source.",
    )
