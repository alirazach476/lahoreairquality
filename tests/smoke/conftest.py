"""Fixtures for the local ingestion smoke suite.

Requires PostgreSQL, MinIO, and Redpanda (see ``scripts/run_smoke_test.py``).
External OpenAQ / Open-Meteo HTTP calls are always mocked.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from lahore_air_quality.config import get_settings
from lahore_air_quality.db.base import Base
from lahore_air_quality.db.session import dispose_engine, get_engine


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "smoke: end-to-end local ingestion pipeline (mocked external APIs)",
    )


def _require_or_skip(reason: str) -> None:
    if os.environ.get("RUN_SMOKE_TESTS", "").strip() == "1":
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def smoke_settings():
    """Reload settings from the environment / ``.env`` for the smoke session."""
    get_settings.cache_clear()
    dispose_engine()
    return get_settings()


@pytest.fixture(scope="session")
def smoke_engine(smoke_settings) -> Iterator[Engine]:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        dispose_engine()
        _require_or_skip(f"PostgreSQL unavailable for smoke tests: {type(exc).__name__}")
    yield engine
    dispose_engine()


@pytest.fixture(scope="session")
def smoke_schema(smoke_engine: Engine) -> Iterator[None]:
    with smoke_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
    import lahore_air_quality.db.models  # noqa: F401

    Base.metadata.create_all(bind=smoke_engine)
    yield


@pytest.fixture(scope="session")
def smoke_minio(smoke_settings) -> Any:
    """Return an S3 object store when MinIO is reachable."""
    from lahore_aqi_consumer.storage.s3 import ObjectStoreError, S3ObjectStore

    store = S3ObjectStore.from_settings(smoke_settings)
    try:
        store.ensure_bucket()
        probe_key = f"smoke/_probe/{uuid.uuid4().hex}.json"
        store.put_json(key=probe_key, document={"ok": True})
        assert store.exists(key=probe_key)
    except (ObjectStoreError, Exception) as exc:  # noqa: BLE001
        _require_or_skip(f"MinIO/S3 unavailable for smoke tests: {type(exc).__name__}")
    return store


@pytest.fixture(scope="session")
def smoke_brokers(smoke_settings) -> str:
    brokers = smoke_settings.redpanda_brokers
    try:
        from confluent_kafka.admin import AdminClient
    except ImportError:
        _require_or_skip("confluent-kafka is required for smoke tests")

    admin = AdminClient({"bootstrap.servers": brokers})
    try:
        meta = admin.list_topics(timeout=8)
    except Exception as exc:  # noqa: BLE001
        _require_or_skip(f"Redpanda unavailable for smoke tests: {type(exc).__name__}")
    if not meta.brokers:
        _require_or_skip("Redpanda returned no brokers")
    return brokers


@pytest.fixture
def smoke_topics(smoke_brokers: str) -> Iterator[tuple[str, str]]:
    """Create isolated AQ/weather topics for one smoke run; delete afterward."""
    from confluent_kafka.admin import AdminClient, NewTopic

    run_id = uuid.uuid4().hex[:10]
    aq_topic = f"smoke.aq.{run_id}"
    wx_topic = f"smoke.weather.{run_id}"
    admin = AdminClient({"bootstrap.servers": smoke_brokers})
    futures = admin.create_topics(
        [
            NewTopic(aq_topic, num_partitions=1, replication_factor=1),
            NewTopic(wx_topic, num_partitions=1, replication_factor=1),
        ]
    )
    for topic, future in futures.items():
        try:
            future.result(timeout=20)
        except Exception as exc:  # noqa: BLE001
            # Topic may already exist from a prior interrupted run.
            if "already exists" not in str(exc).lower() and "TOPIC_ALREADY_EXISTS" not in str(
                type(exc).__name__
            ):
                _require_or_skip(f"Unable to create smoke topic {topic}: {exc}")

    # Brief settle so metadata propagates to producers.
    time.sleep(0.5)
    yield aq_topic, wx_topic

    try:
        delete_futures = admin.delete_topics([aq_topic, wx_topic])
        for future in delete_futures.values():
            try:
                future.result(timeout=10)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture(autouse=True)
def _smoke_truncate(request: pytest.FixtureRequest) -> Iterator[None]:
    """Truncate raw tables before each smoke test that uses the DB."""
    if request.node.get_closest_marker("smoke") is None:
        yield
        return
    if "smoke_engine" not in request.fixturenames:
        yield
        return
    engine: Engine = request.getfixturevalue("smoke_engine")
    request.getfixturevalue("smoke_schema")
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
