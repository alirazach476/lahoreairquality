"""Normalized weather observations."""

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


class WeatherObservation(Base):
    """Weather snapshot at a geographic point and observation time.

    Idempotency key: ``(source, latitude, longitude, observed_at)``.
    """

    __tablename__ = "weather_observations"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "latitude",
            "longitude",
            "observed_at",
            name="uq_weather_obs_source_lat_lon_observed_at",
        ),
        Index("ix_weather_obs_observed_at", "observed_at"),
        Index("ix_weather_obs_ingested_at", "ingested_at"),
        Index("ix_weather_obs_raw_record_id", "raw_record_id"),
        {"schema": "raw"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    relative_humidity_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    precipitation_mm: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    wind_speed_ms: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    wind_direction_deg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    pressure_hpa: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    raw_record_id: Mapped[str] = mapped_column(String(256), nullable=False)
