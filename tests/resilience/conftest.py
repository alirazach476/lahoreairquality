"""Shared fixtures for controlled failure simulations."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from lahore_air_quality.db.repository import InsertResult
from lahore_aqi_consumer.processing import EventProcessor
from lahore_aqi_consumer.storage.postgres import (
    PostgresObservationWriter,
    PostgresWriteError,
    PostgresWriteResult,
)
from lahore_aqi_consumer.storage.s3 import ObjectPutResult, ObjectStoreError


def make_envelope(
    *,
    event_id: str = "openaq:501:abc",
    kind: str = "air_quality",
    source: str = "openaq",
    observed_at: str = "2026-10-24T05:00:00+00:00",
    ingested_at: str = "2026-10-24T06:00:00+00:00",
    normalized: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if normalized is None:
        if kind == "air_quality":
            normalized = {
                "station_id": "9001",
                "pollutant": "pm25",
                "value": "42.5",
                "unit": "µg/m³",
                "observed_at": observed_at,
                "source": "openaq",
                "raw_record_id": event_id,
            }
        else:
            normalized = {
                "latitude": "31.520400",
                "longitude": "74.358700",
                "temperature_c": "28.5",
                "observed_at": observed_at,
                "source": "open-meteo",
                "raw_record_id": event_id,
            }
            source = "open-meteo"
    return {
        "schema": {"name": "lahore_aqi.ingestion_event", "version": "1.0.0"},
        "event_id": event_id,
        "idempotency_key": event_id,
        "source": source,
        "record_kind": kind,
        "event_timestamp": observed_at,
        "ingested_at": ingested_at,
        "normalized": normalized,
        "raw": {"fixture": True},
    }


class FakeObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self.fail = False
        self.put_calls = 0

    def exists(self, *, key: str) -> bool:
        if self.fail:
            raise ObjectStoreError("object store unavailable")
        return key in self.objects

    def put_json(self, *, key: str, document: dict[str, Any]) -> ObjectPutResult:
        self.put_calls += 1
        if self.fail:
            raise ObjectStoreError("object store unavailable")
        existed = key in self.objects
        self.objects[key] = document
        return ObjectPutResult(bucket="test", key=key, already_existed=existed)


def pg_writer(
    *,
    duplicate: bool = False,
    fail: bool = False,
    fail_once: bool = False,
) -> PostgresObservationWriter:
    writer = MagicMock(spec=PostgresObservationWriter)
    state = {"calls": 0}

    def _write(_envelope: Any) -> PostgresWriteResult:
        state["calls"] += 1
        if fail:
            raise PostgresWriteError("db down")
        if fail_once and state["calls"] == 1:
            raise PostgresWriteError("db down temporarily")
        if duplicate:
            return PostgresWriteResult(
                payload=InsertResult(False, "duplicate_raw_record"),
                observation=InsertResult(False, "duplicate_observation"),
            )
        return PostgresWriteResult(
            payload=InsertResult(True, "inserted"),
            observation=InsertResult(True, "inserted"),
        )

    writer.write.side_effect = _write
    return writer


@pytest.fixture
def envelope_factory():
    return make_envelope


@pytest.fixture
def processor_factory():
    def _make(*, store: FakeObjectStore | None = None, pg: Any = None) -> EventProcessor:
        return EventProcessor(
            object_store=store or FakeObjectStore(),
            postgres_writer=pg or pg_writer(),
        )

    return _make


def dumps(envelope: dict[str, Any]) -> bytes:
    return json.dumps(envelope).encode("utf-8")
