"""Persistence adapters for the consumer (S3 + PostgreSQL)."""

from lahore_aqi_consumer.storage.postgres import (
    PostgresObservationWriter,
    PostgresWriteError,
    PostgresWriteResult,
)
from lahore_aqi_consumer.storage.s3 import (
    ObjectPutResult,
    ObjectStore,
    ObjectStoreError,
    S3ObjectStore,
    build_raw_object_key,
)

__all__ = [
    "ObjectPutResult",
    "ObjectStore",
    "ObjectStoreError",
    "PostgresObservationWriter",
    "PostgresWriteError",
    "PostgresWriteResult",
    "S3ObjectStore",
    "build_raw_object_key",
]
