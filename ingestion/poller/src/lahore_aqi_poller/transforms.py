"""Convert client observation bundles into publishable ingestion events."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from lahore_aqi_poller.clients.openaq.models import ObservationBundle
from lahore_aqi_poller.clients.openmeteo.models import WeatherObservationBundle
from lahore_aqi_poller.events import IngestionEvent

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def air_quality_bundle_to_event(
    bundle: ObservationBundle,
    *,
    ingested_at: datetime | None = None,
) -> IngestionEvent | None:
    """Build an idempotent AQ event; return None if the record is unusable.

    Never fabricates measurement values — only fields present on the bundle.
    """
    try:
        obs = bundle.observation
        if not obs.raw_record_id or not obs.pollutant:
            logger.warning(
                "reject_air_quality_record",
                extra={"reason": "missing_identity_fields"},
            )
            return None
        if obs.value is None:  # pragma: no cover - pydantic requires value
            logger.warning(
                "reject_air_quality_record",
                extra={"reason": "missing_value", "raw_record_id": obs.raw_record_id},
            )
            return None

        stamp = ingested_at or _utc_now()
        key = obs.raw_record_id
        normalized = obs.model_dump(mode="json")
        return IngestionEvent(
            event_id=key,
            idempotency_key=key,
            source="openaq",
            record_kind="air_quality",
            ingested_at=stamp,
            observed_at=obs.observed_at,
            normalized=normalized,
            raw=dict(bundle.raw_payload),
        )
    except Exception:
        logger.exception("reject_air_quality_record_exception")
        return None


def weather_bundle_to_event(
    bundle: WeatherObservationBundle,
    *,
    ingested_at: datetime | None = None,
) -> IngestionEvent | None:
    """Build an idempotent weather event; return None if unusable.

    Does not invent missing weather variables — nulls stay null.
    """
    try:
        obs = bundle.observation
        if not obs.raw_record_id:
            logger.warning(
                "reject_weather_record",
                extra={"reason": "missing_raw_record_id"},
            )
            return None
        if not obs.has_any_measurement():
            logger.warning(
                "reject_weather_record",
                extra={
                    "reason": "no_measurements",
                    "raw_record_id": obs.raw_record_id,
                },
            )
            return None

        stamp = ingested_at or _utc_now()
        key = obs.raw_record_id
        normalized = obs.model_dump(mode="json")
        raw: dict[str, Any] = dict(bundle.raw_payload)
        if bundle.response_meta:
            raw = {**raw, "response_meta": bundle.response_meta}
        return IngestionEvent(
            event_id=key,
            idempotency_key=key,
            source="open-meteo",
            record_kind="weather",
            ingested_at=stamp,
            observed_at=obs.observed_at,
            normalized=normalized,
            raw=raw,
        )
    except Exception:
        logger.exception("reject_weather_record_exception")
        return None
