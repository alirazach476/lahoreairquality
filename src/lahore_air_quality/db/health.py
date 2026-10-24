"""Database connectivity health checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from lahore_air_quality.db.session import get_engine

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    """Result of a database health probe."""

    healthy: bool
    message: str
    server_version: str | None = None
    details: dict[str, Any] | None = None


def check_database_health(engine: Engine | None = None) -> DatabaseHealth:
    """Ping PostgreSQL and return a structured health result.

    Secrets are never included in the returned message or logs.
    """
    eng = engine or get_engine()
    try:
        with eng.connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar_one()
            conn.execute(text("SELECT 1"))
        message = "PostgreSQL connection OK"
        logger.info("Database health check passed (server_version=%s)", version)
        return DatabaseHealth(
            healthy=True,
            message=message,
            server_version=str(version),
        )
    except SQLAlchemyError as exc:
        # Log exception type/class only — connection strings may embed secrets.
        logger.exception(
            "Database health check failed: %s",
            type(exc).__name__,
        )
        return DatabaseHealth(
            healthy=False,
            message=f"PostgreSQL connection failed: {type(exc).__name__}",
            details={"error_type": type(exc).__name__},
        )
