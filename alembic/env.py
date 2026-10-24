"""Alembic environment — loads DB URL from application Settings (not this file)."""

from __future__ import annotations

import logging
import sys
from logging.config import fileConfig
from pathlib import Path

# Ensure the installable package under src/ is importable when running Alembic
# from the repository root without an editable install.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from alembic import context
from sqlalchemy import engine_from_config, pool

from lahore_air_quality.config import get_settings
from lahore_air_quality.db import models as _models  # noqa: F401 — register mappers
from lahore_air_quality.db.base import Base

logger = logging.getLogger("alembic.env")

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure_url() -> str:
    """Resolve the SQLAlchemy URL from environment-backed settings."""
    settings = get_settings()
    url = settings.postgres_dsn
    # Never log the URL — it embeds credentials.
    logger.info(
        "Alembic targeting PostgreSQL host=%s db=%s",
        settings.postgres_host,
        settings.postgres_db,
    )
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script generation)."""
    url = _configure_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="public",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _configure_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema="public",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
