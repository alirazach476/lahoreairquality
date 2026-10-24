"""Engine and session factory with connection pooling.

Credentials are read from :mod:`lahore_air_quality.config` — never hard-coded.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from lahore_air_quality.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Pool defaults sized for local/dev and modest API traffic.
_DEFAULT_POOL_SIZE = 5
_DEFAULT_MAX_OVERFLOW = 10
_DEFAULT_POOL_TIMEOUT_SECONDS = 30
_DEFAULT_POOL_RECYCLE_SECONDS = 1800


def _create_engine(settings: Settings) -> Engine:
    """Build a pooled SQLAlchemy engine for PostgreSQL."""
    engine = create_engine(
        settings.postgres_dsn,
        pool_size=_DEFAULT_POOL_SIZE,
        max_overflow=_DEFAULT_MAX_OVERFLOW,
        pool_timeout=_DEFAULT_POOL_TIMEOUT_SECONDS,
        pool_recycle=_DEFAULT_POOL_RECYCLE_SECONDS,
        pool_pre_ping=True,
        future=True,
        connect_args={"connect_timeout": 5},
    )

    @event.listens_for(engine, "connect")
    def _set_utc(dbapi_connection: object, _connection_record: object) -> None:
        """Force session TimeZone to UTC for consistent timestamptz behaviour."""
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("SET TIME ZONE 'UTC'")
        finally:
            cursor.close()

    logger.info(
        "Created SQLAlchemy engine for PostgreSQL host=%s db=%s pool_size=%s",
        settings.postgres_host,
        settings.postgres_db,
        _DEFAULT_POOL_SIZE,
    )
    return engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide pooled engine (cached)."""
    return _create_engine(get_settings())


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Return a cached ``sessionmaker`` bound to the pooled engine."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


def dispose_engine() -> None:
    """Dispose the cached engine and clear factories (used in tests/shutdown)."""
    try:
        engine = get_engine()
    except Exception:  # noqa: BLE001 - cache may be empty or settings invalid
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        return
    engine.dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    logger.info("Disposed SQLAlchemy engine")


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations.

    Commits on success; rolls back and re-raises on error. Does not swallow
    exceptions.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
