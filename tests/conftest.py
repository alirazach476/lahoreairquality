"""Shared pytest fixtures and markers."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from lahore_air_quality.config import get_settings
from lahore_air_quality.db.base import Base
from lahore_air_quality.db.session import dispose_engine, get_engine


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "postgres: tests that require a reachable PostgreSQL instance",
    )
    config.addinivalue_line(
        "markers",
        "integration: live external API tests (opt-in; see docs/testing.md)",
    )


@pytest.fixture(scope="session")
def postgres_engine() -> Engine:
    """Return an engine if PostgreSQL is reachable; otherwise skip the session."""
    get_settings.cache_clear()
    dispose_engine()
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        dispose_engine()
        pytest.skip(f"PostgreSQL is not available: {type(exc).__name__}")
    yield engine
    dispose_engine()


@pytest.fixture(scope="session")
def migrated_schema(postgres_engine: Engine) -> None:
    """Ensure schemas/extensions exist and ORM tables are present for tests.

    Uses ``create_all`` for isolation from Alembic when running unit/integration
    tests locally. Apply ``alembic upgrade head`` for real environments.
    """
    with postgres_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
    # Import models so metadata is populated.
    import lahore_air_quality.db.models  # noqa: F401

    Base.metadata.create_all(bind=postgres_engine)
    yield
    Base.metadata.drop_all(bind=postgres_engine)


@pytest.fixture(autouse=True)
def _truncate_raw_tables(
    request: pytest.FixtureRequest,
) -> None:
    """Truncate observation tables before each postgres-marked test."""
    if request.node.get_closest_marker("postgres") is None:
        yield
        return
    if "postgres_engine" not in request.fixturenames:
        yield
        return
    engine: Engine = request.getfixturevalue("postgres_engine")
    request.getfixturevalue("migrated_schema")
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE "
                "raw.air_quality_observations, "
                "raw.weather_observations, "
                "raw.ingestion_payloads "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield
