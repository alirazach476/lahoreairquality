"""S3-compatible archival of original ingestion event JSON."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_SAFE_KEY = re.compile(r"[^A-Za-z0-9._/-]+")


class ObjectStoreError(Exception):
    """Raised when an object-store operation fails (retryable)."""


@dataclass(frozen=True, slots=True)
class ObjectPutResult:
    bucket: str
    key: str
    already_existed: bool = False


class ObjectStore(Protocol):
    def put_json(self, *, key: str, document: dict[str, Any]) -> ObjectPutResult: ...

    def exists(self, *, key: str) -> bool: ...


def build_raw_object_key(
    *,
    record_kind: str,
    source: str,
    event_id: str,
    event_timestamp: datetime,
) -> str:
    """Deterministic object key for an event (safe for retries / dedupe).

    Format: ``raw/{kind}/{source}/{YYYY}/{MM}/{DD}/{sanitized_event_id}.json``
    """
    day = event_timestamp.strftime("%Y/%m/%d")
    safe_id = _SAFE_KEY.sub("_", event_id.strip())[:200] or "unknown"
    safe_kind = _SAFE_KEY.sub("_", record_kind.strip()) or "unknown"
    safe_source = _SAFE_KEY.sub("_", source.strip()) or "unknown"
    return f"raw/{safe_kind}/{safe_source}/{day}/{safe_id}.json"


class S3ObjectStore:
    """boto3-backed S3/MinIO client. Credentials come from Settings — never logged."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "us-east-1",
        client: Any | None = None,
    ) -> None:
        self._bucket = bucket
        if client is not None:
            self._client = client
        else:
            import boto3
            from botocore.client import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name=region,
                # Path-style works with MinIO and Adobe S3Mock local endpoints.
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
        logger.info(
            "s3_client_created",
            extra={"endpoint_url": endpoint_url, "bucket": bucket, "region": region},
        )

    @classmethod
    def from_settings(cls, settings: Any | None = None) -> S3ObjectStore:
        if settings is None:
            from lahore_air_quality.config import get_settings

            settings = get_settings()
        return cls(
            endpoint_url=settings.s3_endpoint_url,
            bucket=settings.s3_bucket,
            access_key_id=settings.aws_access_key_id.get_secret_value(),
            secret_access_key=settings.aws_secret_access_key.get_secret_value(),
            region=settings.aws_region,
        )

    def ensure_bucket(self) -> None:
        """Create the bucket if missing (local MinIO convenience)."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self._bucket)
                logger.info("s3_bucket_created", extra={"bucket": self._bucket})
            except Exception as exc:
                raise ObjectStoreError(
                    f"Unable to ensure bucket {self._bucket!r}: {type(exc).__name__}"
                ) from exc

    def exists(self, *, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception as exc:
            code = _error_code(exc)
            if code in {"404", "NoSuchKey", "NotFound", "404 Not Found"}:
                return False
            raise ObjectStoreError(
                f"head_object failed for s3://{self._bucket}/{key}: {type(exc).__name__}"
            ) from exc

    def put_json(self, *, key: str, document: dict[str, Any]) -> ObjectPutResult:
        """Put JSON at a deterministic key. Retries overwrite the same object only."""
        existed = False
        try:
            existed = self.exists(key=key)
        except ObjectStoreError:
            # Existence probe failed — still attempt put; surface put errors.
            logger.warning(
                "s3_exists_probe_failed",
                extra={"bucket": self._bucket, "key": key},
            )

        body = json.dumps(document, ensure_ascii=False, default=str).encode("utf-8")
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
        except Exception as exc:
            logger.exception(
                "s3_put_failed",
                extra={"bucket": self._bucket, "key": key, "error_type": type(exc).__name__},
            )
            raise ObjectStoreError(
                f"put_object failed for s3://{self._bucket}/{key}: {type(exc).__name__}"
            ) from exc

        logger.info(
            "s3_put_ok",
            extra={
                "bucket": self._bucket,
                "key": key,
                "bytes": len(body),
                "already_existed": existed,
            },
        )
        return ObjectPutResult(bucket=self._bucket, key=key, already_existed=existed)


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        err = response.get("Error") or {}
        if isinstance(err, dict) and "Code" in err:
            return str(err["Code"])
    return type(exc).__name__
