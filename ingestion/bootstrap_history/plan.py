"""Build a bootstrap plan (no writes) from discovery + configured window."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ingestion.bootstrap_history.discover import (
    DiscoveryReport,
    discover_pm_sensors,
)
from ingestion.bootstrap_history.settings import (
    DEFAULT_AQ_CHUNK_DAYS,
    DEFAULT_LOOKBACK_DAYS,
    OPEN_METEO_ATTRIBUTION,
    RAW_OBJECT_PREFIX,
    TARGET_TABLES,
    TARGET_TABLES_WEATHER_ONLY,
    BootstrapWindow,
    default_window,
    effective_weather_persist_end,
    iter_chunks,
)
from lahore_air_quality.config import Settings, get_settings
from lahore_aqi_poller.clients.openaq.client import OpenAQClient
from lahore_aqi_poller.clients.openaq.models import OpenAQLocation

BootstrapMode = Literal["full", "weather_only"]


@dataclass
class BootstrapPlan:
    """Operator-facing plan printed before ``--execute``."""

    window: BootstrapWindow
    weather_latitude: float
    weather_longitude: float
    target_tables: tuple[str, ...]
    object_storage_prefix: str
    aq_chunk_days: int
    discovery: DiscoveryReport
    mode: BootstrapMode = "full"
    locations: list[OpenAQLocation] = field(repr=False, default_factory=list)
    estimated_aq_sensor_chunks: int = 0
    estimated_weather_days: int = 0
    resource_notes: list[str] = field(default_factory=list)
    data_provenance: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    attribution: list[str] = field(default_factory=list)

    @property
    def include_air_quality(self) -> bool:
        return self.mode == "full"

    def weather_archive_calendar_dates(self) -> dict[str, str]:
        """Calendar dates sent to Open-Meteo (may include a partial final day)."""
        return {
            "start_date": self.window.start.date().isoformat(),
            "end_date": self.window.end.date().isoformat(),
        }

    def weather_persist_end_utc(self) -> str:
        """Plan-time persist ceiling (execute recomputes at run time)."""
        return effective_weather_persist_end(self.window.end).isoformat()

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "requested_window": self.window.as_dict(),
            # Backward-compatible alias for callers expecting "window".
            "window": self.window.as_dict(),
            "weather_archive_calendar_dates": self.weather_archive_calendar_dates(),
            "weather_persist_end_utc": self.weather_persist_end_utc(),
            "weather_coordinates": {
                "latitude": self.weather_latitude,
                "longitude": self.weather_longitude,
                "provenance": "model-derived Open-Meteo Historical Weather API "
                "(not in-situ / ground-station measurements)",
            },
            "air_quality_provenance": (
                "measured OpenAQ v3 sensor observations (only sensors discovered at runtime)"
                if self.include_air_quality
                else "skipped (weather_only mode — OpenAQ not called)"
            ),
            "target_tables": list(self.target_tables),
            "object_storage_prefix": self.object_storage_prefix,
            "aq_chunk_days": self.aq_chunk_days,
            "discovery": self.discovery.as_dict(),
            "estimated_aq_sensor_chunks": self.estimated_aq_sensor_chunks,
            "estimated_weather_days": self.estimated_weather_days,
            "resource_notes": self.resource_notes,
            "data_provenance": self.data_provenance,
            "warnings": self.warnings,
            "attribution": self.attribution,
        }


def build_bootstrap_plan(
    *,
    client: OpenAQClient | None = None,
    settings: Settings | None = None,
    window: BootstrapWindow | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    aq_chunk_days: int = DEFAULT_AQ_CHUNK_DAYS,
    radius_m: int | None = None,
    weather_only: bool = False,
) -> BootstrapPlan:
    """Assemble a plan. Performs **no** database writes.

    ``weather_only=True`` skips OpenAQ entirely (no API key required) and plans
    only the Open-Meteo archive import.
    """
    cfg = settings or get_settings()
    win = window or default_window(lookback_days=lookback_days)
    weather_days = max(1, int((win.end - win.start).total_seconds() // 86400) or 1)

    if weather_only:
        return _weather_only_plan(cfg=cfg, win=win, weather_days=weather_days)

    owns_client = client is None
    openaq = client or OpenAQClient.from_settings(cfg)
    try:
        locations, discovery = discover_pm_sensors(openaq, radius_m=radius_m)
    finally:
        if owns_client:
            openaq.close()

    chunks = iter_chunks(win, chunk_days=aq_chunk_days)
    sensor_n = len(discovery.target_sensors)
    estimated_chunks = sensor_n * len(chunks)

    warnings: list[str] = []
    for sensor in discovery.target_sensors:
        if sensor.location_last is not None and sensor.location_last < win.start:
            warnings.append(
                f"sensor {sensor.sensor_id} ({sensor.pollutant}) last seen "
                f"{sensor.location_last.isoformat()} before window start — "
                "historical fetch may return empty"
            )
        if sensor.location_first is not None and sensor.location_first > win.end:
            warnings.append(
                f"sensor {sensor.sensor_id} ({sensor.pollutant}) first seen "
                f"{sensor.location_first.isoformat()} after window end — "
                "historical fetch may return empty"
            )

    persist_end = effective_weather_persist_end(win.end)
    resource_notes = [
        f"OpenAQ: ~{estimated_chunks} paginated sensor×chunk requests "
        f"({sensor_n} PM sensors × {len(chunks)} chunks of {aq_chunk_days}d), "
        "throttled to ~1 req/s (free-tier safe).",
        f"Open-Meteo archive request: calendar {win.start.date().isoformat()}.."
        f"{win.end.date().isoformat()} (~{weather_days} day(s)) at "
        f"lat={cfg.lahore_latitude}, lon={cfg.lahore_longitude}.",
        f"Requested window end: {win.end.isoformat()}; weather rows persisted "
        f"only through completed UTC hour ≤ {persist_end.isoformat()} "
        "(archive may return later hours on the final calendar day — those are skipped).",
        "Writes use existing idempotent inserts (ON CONFLICT DO NOTHING) — "
        "reruns do not duplicate rows or delete data.",
        "Original API JSON is archived under the existing MinIO/S3 raw/ prefix "
        "when object storage is reachable; Postgres normalized rows always attempted.",
        "Missing OpenAQ measurements are skipped — never filled with invented values.",
        "Respect Open-Meteo free/non-commercial rate limits; do not fabricate values.",
    ]

    return BootstrapPlan(
        mode="full",
        window=win,
        weather_latitude=float(cfg.lahore_latitude),
        weather_longitude=float(cfg.lahore_longitude),
        target_tables=TARGET_TABLES,
        object_storage_prefix=RAW_OBJECT_PREFIX,
        aq_chunk_days=aq_chunk_days,
        discovery=discovery,
        locations=locations,
        estimated_aq_sensor_chunks=estimated_chunks,
        estimated_weather_days=weather_days,
        resource_notes=resource_notes,
        data_provenance={
            "air_quality": "openaq_measured",
            "weather": "open_meteo_model_historical",
        },
        warnings=warnings,
        attribution=[OPEN_METEO_ATTRIBUTION, "OpenAQ: attribute OpenAQ and original sources."],
    )


def _weather_only_plan(
    *,
    cfg: Settings,
    win: BootstrapWindow,
    weather_days: int,
) -> BootstrapPlan:
    discovery = DiscoveryReport(
        notes=[
            "weather_only mode: OpenAQ discovery skipped (no OPENAQ_API_KEY required).",
            "Air-quality tables will not be written in this run.",
        ]
    )
    persist_end = effective_weather_persist_end(win.end)
    resource_notes = [
        f"Open-Meteo archive request: calendar {win.start.date().isoformat()}.."
        f"{win.end.date().isoformat()} (~{weather_days} day(s)) at "
        f"lat={cfg.lahore_latitude}, lon={cfg.lahore_longitude} "
        "(public endpoint; no API key).",
        f"Requested window end: {win.end.isoformat()}; weather rows persisted "
        f"only through completed UTC hour ≤ {persist_end.isoformat()} "
        "(archive may return later hours on the final calendar day — those are skipped).",
        "Weather values are model/reanalysis-derived — not labeled as ground stations.",
        "Writes use existing idempotent inserts (ON CONFLICT DO NOTHING).",
        "Respect Open-Meteo free/non-commercial usage terms and rate limits.",
        OPEN_METEO_ATTRIBUTION,
    ]
    return BootstrapPlan(
        mode="weather_only",
        window=win,
        weather_latitude=float(cfg.lahore_latitude),
        weather_longitude=float(cfg.lahore_longitude),
        target_tables=TARGET_TABLES_WEATHER_ONLY,
        object_storage_prefix=RAW_OBJECT_PREFIX,
        aq_chunk_days=DEFAULT_AQ_CHUNK_DAYS,
        discovery=discovery,
        locations=[],
        estimated_aq_sensor_chunks=0,
        estimated_weather_days=weather_days,
        resource_notes=resource_notes,
        data_provenance={
            "air_quality": "skipped",
            "weather": "open_meteo_model_historical",
        },
        warnings=[],
        attribution=[OPEN_METEO_ATTRIBUTION],
    )
