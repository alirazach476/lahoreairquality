"""Initial raw payloads and observation tables.

Revision ID: 20261024_0001
Revises:
Create Date: 2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261024_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE SCHEMA IF NOT EXISTS raw")

    op.create_table(
        "ingestion_payloads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("record_kind", sa.String(length=32), nullable=False),
        sa.Column("raw_record_id", sa.String(length=256), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "raw_record_id",
            name="uq_ingestion_payloads_source_raw_record_id",
        ),
        schema="raw",
    )
    op.create_index(
        "ix_ingestion_payloads_ingested_at",
        "ingestion_payloads",
        ["ingested_at"],
        schema="raw",
    )
    op.create_index(
        "ix_ingestion_payloads_kind_ingested_at",
        "ingestion_payloads",
        ["record_kind", "ingested_at"],
        schema="raw",
    )
    # BRIN supports efficient range scans as the append-only raw archive grows.
    op.execute(
        "CREATE INDEX ix_ingestion_payloads_ingested_at_brin "
        "ON raw.ingestion_payloads USING BRIN (ingested_at)"
    )

    op.create_table(
        "air_quality_observations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("observation_id", sa.String(length=128), nullable=True),
        sa.Column("station_id", sa.String(length=128), nullable=False),
        sa.Column("location_name", sa.String(length=256), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("pollutant", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Numeric(precision=16, scale=6), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("raw_record_id", sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "station_id",
            "pollutant",
            "observed_at",
            name="uq_aq_obs_source_station_pollutant_observed_at",
        ),
        schema="raw",
    )
    op.create_index(
        "ix_aq_obs_observed_at",
        "air_quality_observations",
        ["observed_at"],
        schema="raw",
    )
    op.create_index(
        "ix_aq_obs_station_observed_at",
        "air_quality_observations",
        ["station_id", "observed_at"],
        schema="raw",
    )
    op.create_index(
        "ix_aq_obs_pollutant_observed_at",
        "air_quality_observations",
        ["pollutant", "observed_at"],
        schema="raw",
    )
    op.create_index(
        "ix_aq_obs_ingested_at",
        "air_quality_observations",
        ["ingested_at"],
        schema="raw",
    )
    op.create_index(
        "ix_aq_obs_raw_record_id",
        "air_quality_observations",
        ["raw_record_id"],
        schema="raw",
    )
    op.execute(
        "CREATE INDEX ix_aq_obs_observed_at_brin "
        "ON raw.air_quality_observations USING BRIN (observed_at)"
    )

    op.create_table(
        "weather_observations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("temperature_c", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column(
            "relative_humidity_pct",
            sa.Numeric(precision=5, scale=2),
            nullable=True,
        ),
        sa.Column("precipitation_mm", sa.Numeric(precision=8, scale=3), nullable=True),
        sa.Column("wind_speed_ms", sa.Numeric(precision=8, scale=3), nullable=True),
        sa.Column(
            "wind_direction_deg",
            sa.Numeric(precision=6, scale=2),
            nullable=True,
        ),
        sa.Column("pressure_hpa", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("raw_record_id", sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "latitude",
            "longitude",
            "observed_at",
            name="uq_weather_obs_source_lat_lon_observed_at",
        ),
        schema="raw",
    )
    op.create_index(
        "ix_weather_obs_observed_at",
        "weather_observations",
        ["observed_at"],
        schema="raw",
    )
    op.create_index(
        "ix_weather_obs_ingested_at",
        "weather_observations",
        ["ingested_at"],
        schema="raw",
    )
    op.create_index(
        "ix_weather_obs_raw_record_id",
        "weather_observations",
        ["raw_record_id"],
        schema="raw",
    )
    op.execute(
        "CREATE INDEX ix_weather_obs_observed_at_brin "
        "ON raw.weather_observations USING BRIN (observed_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS raw.ix_weather_obs_observed_at_brin")
    op.drop_index(
        "ix_weather_obs_raw_record_id",
        table_name="weather_observations",
        schema="raw",
    )
    op.drop_index(
        "ix_weather_obs_ingested_at",
        table_name="weather_observations",
        schema="raw",
    )
    op.drop_index(
        "ix_weather_obs_observed_at",
        table_name="weather_observations",
        schema="raw",
    )
    op.drop_table("weather_observations", schema="raw")

    op.execute("DROP INDEX IF EXISTS raw.ix_aq_obs_observed_at_brin")
    op.drop_index(
        "ix_aq_obs_raw_record_id",
        table_name="air_quality_observations",
        schema="raw",
    )
    op.drop_index(
        "ix_aq_obs_ingested_at",
        table_name="air_quality_observations",
        schema="raw",
    )
    op.drop_index(
        "ix_aq_obs_pollutant_observed_at",
        table_name="air_quality_observations",
        schema="raw",
    )
    op.drop_index(
        "ix_aq_obs_station_observed_at",
        table_name="air_quality_observations",
        schema="raw",
    )
    op.drop_index(
        "ix_aq_obs_observed_at",
        table_name="air_quality_observations",
        schema="raw",
    )
    op.drop_table("air_quality_observations", schema="raw")

    op.execute("DROP INDEX IF EXISTS raw.ix_ingestion_payloads_ingested_at_brin")
    op.drop_index(
        "ix_ingestion_payloads_kind_ingested_at",
        table_name="ingestion_payloads",
        schema="raw",
    )
    op.drop_index(
        "ix_ingestion_payloads_ingested_at",
        table_name="ingestion_payloads",
        schema="raw",
    )
    op.drop_table("ingestion_payloads", schema="raw")
