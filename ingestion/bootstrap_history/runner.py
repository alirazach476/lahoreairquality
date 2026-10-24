"""Execute a bootstrap plan: fetch history and dual-write (idempotent)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from ingestion.bootstrap_history.discover import location_by_id
from ingestion.bootstrap_history.persist import (
    PersistStats,
    build_event_processor,
    persist_event,
)
from ingestion.bootstrap_history.plan import BootstrapPlan
from ingestion.bootstrap_history.settings import (
    OPEN_METEO_ATTRIBUTION,
    as_utc,
    effective_weather_persist_end,
    is_within_bootstrap_window,
    iter_chunks,
)
from lahore_air_quality.config import Settings, get_settings
from lahore_aqi_poller.clients.openaq.client import OpenAQClient
from lahore_aqi_poller.clients.openmeteo.client import OpenMeteoClient
from lahore_aqi_poller.clients.openmeteo.models import WeatherObservationBundle
from lahore_aqi_poller.transforms import air_quality_bundle_to_event, weather_bundle_to_event

logger = logging.getLogger(__name__)


@dataclass
class BootstrapResult:
    executed: bool
    plan: dict[str, Any]
    storage_mode: str
    air_quality: PersistStats = field(default_factory=PersistStats)
    weather: PersistStats = field(default_factory=PersistStats)
    aq_observations_fetched: int = 0
    aq_observations_skipped_outside_window: int = 0
    weather_observations_fetched: int = 0
    weather_observations_eligible: int = 0
    weather_observations_skipped_future: int = 0
    weather_persist_end_utc: str | None = None
    sensors_queried: int = 0
    empty_sensor_chunks: int = 0
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "executed": self.executed,
            "plan": self.plan,
            "storage_mode": self.storage_mode,
            "air_quality_persist": self.air_quality.as_dict(),
            "weather_persist": self.weather.as_dict(),
            "aq_observations_fetched": self.aq_observations_fetched,
            "aq_observations_skipped_outside_window": (self.aq_observations_skipped_outside_window),
            "weather_observations_fetched": self.weather_observations_fetched,
            "weather_observations_eligible": self.weather_observations_eligible,
            "weather_observations_skipped_future": (self.weather_observations_skipped_future),
            "weather_persist_end_utc": self.weather_persist_end_utc,
            "sensors_queried": self.sensors_queried,
            "empty_sensor_chunks": self.empty_sensor_chunks,
            "errors": self.errors,
            "notes": self.notes,
        }


def filter_weather_through_persist_end(
    bundles: Sequence[WeatherObservationBundle],
    *,
    persist_end: datetime,
) -> tuple[list[WeatherObservationBundle], list[WeatherObservationBundle]]:
    """Split archive hours into eligible (≤ persist_end UTC) vs skipped future."""
    ceiling = as_utc(persist_end)
    eligible: list[WeatherObservationBundle] = []
    skipped: list[WeatherObservationBundle] = []
    for bundle in bundles:
        observed = as_utc(bundle.observation.observed_at)
        if observed <= ceiling:
            eligible.append(bundle)
        else:
            skipped.append(bundle)
    return eligible, skipped


def execute_bootstrap(
    plan: BootstrapPlan,
    *,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
    openaq_client: OpenAQClient | None = None,
    openmeteo_client: OpenMeteoClient | None = None,
    require_object_store: bool = False,
    now: datetime | None = None,
) -> BootstrapResult:
    """Fetch and persist history. Idempotent; never invents observation values.

    ``now`` overrides the wall clock used for the weather persist ceiling
    (tests only — production omits it).
    """
    cfg = settings or get_settings()
    processor, storage_mode = build_event_processor(
        session_factory,
        settings=cfg,
        require_object_store=require_object_store,
    )
    notes = [
        "Weather = model-derived Open-Meteo historical archive (not ground-station measurements).",
        OPEN_METEO_ATTRIBUTION,
        "Duplicates skipped via existing unique constraints.",
    ]
    if plan.include_air_quality:
        notes.insert(0, "Air quality = measured OpenAQ observations.")
    else:
        notes.insert(0, "weather_only: OpenAQ skipped (no air-quality writes).")

    result = BootstrapResult(
        executed=True,
        plan=plan.as_dict(),
        storage_mode=storage_mode,
        notes=notes,
    )
    if storage_mode == "postgres_only":
        result.notes.append(
            "Object storage was unavailable; original JSON was not archived to S3. "
            "Normalized rows were still written to PostgreSQL."
        )

    owns_openaq = False
    owns_meteo = openmeteo_client is None
    openaq: OpenAQClient | None = None
    meteo = openmeteo_client or OpenMeteoClient.from_settings(cfg)

    try:
        if plan.include_air_quality:
            owns_openaq = openaq_client is None
            openaq = openaq_client or OpenAQClient.from_settings(cfg)
            locations = location_by_id(plan.locations)
            _import_air_quality(plan, openaq, locations, processor, result)
        _import_weather(plan, meteo, processor, result, now=now)
    finally:
        if owns_openaq and openaq is not None:
            openaq.close()
        if owns_meteo:
            meteo.close()

    return result


def _import_air_quality(
    plan: BootstrapPlan,
    client: OpenAQClient,
    locations: dict[int, Any],
    processor: Any,
    result: BootstrapResult,
) -> None:
    chunks = iter_chunks(plan.window, chunk_days=plan.aq_chunk_days)
    for sensor in plan.discovery.target_sensors:
        location = locations.get(sensor.location_id)
        result.sensors_queried += 1
        for chunk in chunks:
            try:
                bundles = client.fetch_historical_measurements(
                    sensor.sensor_id,
                    datetime_from=chunk.start,
                    datetime_to=chunk.end,
                    location=location,
                )
            except Exception as exc:  # noqa: BLE001
                msg = (
                    f"OpenAQ fetch failed sensor_id={sensor.sensor_id} "
                    f"chunk={chunk.start.date()}..{chunk.end.date()}: "
                    f"{type(exc).__name__}"
                )
                logger.exception(msg)
                result.errors.append(msg)
                continue

            if not bundles:
                result.empty_sensor_chunks += 1
                continue

            result.aq_observations_fetched += len(bundles)
            for bundle in bundles:
                if bundle.observation.pollutant not in {"pm25", "pm10"}:
                    continue
                if not is_within_bootstrap_window(bundle.observation.observed_at, plan.window):
                    result.aq_observations_skipped_outside_window += 1
                    logger.info(
                        "Skipping OpenAQ observation outside requested window "
                        "sensor_id=%s observed_at=%s window_end=%s",
                        sensor.sensor_id,
                        bundle.observation.observed_at,
                        plan.window.end.isoformat(),
                    )
                    continue
                event = air_quality_bundle_to_event(bundle)
                if event is None:
                    result.air_quality.rejected += 1
                    continue
                persist_event(processor, event, result.air_quality)


def _import_weather(
    plan: BootstrapPlan,
    client: OpenMeteoClient,
    processor: Any,
    result: BootstrapResult,
    *,
    now: datetime | None = None,
) -> None:
    start_d: date = plan.window.start.date()
    end_d: date = plan.window.end.date()
    persist_end = effective_weather_persist_end(plan.window.end, now=now)
    result.weather_persist_end_utc = persist_end.isoformat()
    result.notes.append(
        f"Weather requested archive calendar {start_d.isoformat()}.."
        f"{end_d.isoformat()}; persist ceiling {persist_end.isoformat()} "
        "(completed UTC hour; future archive hours are not written)."
    )
    try:
        bundles = client.fetch_historical(
            start_date=start_d,
            end_date=end_d,
            latitude=plan.weather_latitude,
            longitude=plan.weather_longitude,
        )
    except Exception as exc:  # noqa: BLE001
        # Log exception type only — never dump response bodies that might hold secrets.
        msg = f"Open-Meteo historical fetch failed: {type(exc).__name__}"
        logger.exception(msg)
        result.errors.append(msg)
        return

    if not bundles:
        result.errors.append(
            "Open-Meteo historical fetch returned no hourly observations "
            f"for {start_d}..{end_d} (empty response — nothing invented)."
        )
        return

    result.weather_observations_fetched = len(bundles)
    eligible, skipped_future = filter_weather_through_persist_end(bundles, persist_end=persist_end)
    result.weather_observations_eligible = len(eligible)
    result.weather_observations_skipped_future = len(skipped_future)
    if skipped_future:
        logger.info(
            "Skipped %s Open-Meteo hour(s) after persist end %s (requested calendar end_date=%s)",
            len(skipped_future),
            persist_end.isoformat(),
            end_d.isoformat(),
        )
        result.notes.append(
            f"Skipped {len(skipped_future)} weather hour(s) later than "
            f"{persist_end.isoformat()}; {len(eligible)} eligible for persist."
        )

    if not eligible:
        result.errors.append(
            "Open-Meteo returned hourly rows but none were at or before the "
            f"persist ceiling {persist_end.isoformat()} "
            f"(fetched={len(bundles)}, skipped_future={len(skipped_future)})."
        )
        return

    for bundle in eligible:
        event = weather_bundle_to_event(bundle)
        if event is None:
            result.weather.rejected += 1
            continue
        persist_event(processor, event, result.weather)
