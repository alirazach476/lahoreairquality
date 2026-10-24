"""Bootstrap history unit tests (mocked OpenAQ / Open-Meteo — no live API)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from ingestion.bootstrap_history.discover import discover_pm_sensors
from ingestion.bootstrap_history.plan import build_bootstrap_plan
from ingestion.bootstrap_history.settings import BootstrapWindow, iter_chunks

from lahore_aqi_poller.clients.openaq.models import (
    Coordinates,
    CountryBase,
    DatetimeObject,
    OpenAQLocation,
    ParameterBase,
    SensorBase,
)


def _location_with_sensors() -> OpenAQLocation:
    return OpenAQLocation(
        id=101,
        name="Lahore Test Site",
        country=CountryBase(code="PK", name="Pakistan"),
        sensors=[
            SensorBase(
                id=501,
                name="PM2.5",
                parameter=ParameterBase(id=1, name="pm25", units="µg/m³"),
            ),
            SensorBase(
                id=502,
                name="O3",
                parameter=ParameterBase(id=2, name="o3", units="ppm"),
            ),
            SensorBase(
                id=503,
                name="PM10",
                parameter=ParameterBase(id=3, name="pm10", units="µg/m³"),
            ),
        ],
        coordinates=Coordinates(latitude=31.52, longitude=74.35),
        datetimeFirst=DatetimeObject(utc="2024-01-01T00:00:00Z", local=None),
        datetimeLast=DatetimeObject(utc="2026-06-01T00:00:00Z", local=None),
    )


def test_discover_keeps_only_pm_sensors() -> None:
    client = MagicMock()
    client.discover_lahore_locations.return_value = [_location_with_sensors()]
    locations, report = discover_pm_sensors(client)
    assert len(locations) == 1
    assert report.locations_found == 1
    assert report.sensors_total == 3
    assert {s.pollutant for s in report.target_sensors} == {"pm25", "pm10"}
    assert {s.sensor_id for s in report.target_sensors} == {501, 503}
    assert any(s["pollutant"] == "o3" for s in report.skipped_sensors)


def test_discover_empty_locations() -> None:
    client = MagicMock()
    client.discover_lahore_locations.return_value = []
    _, report = discover_pm_sensors(client)
    assert report.target_sensors == []
    assert any("No Lahore locations" in n for n in report.notes)


def test_build_plan_uses_discovery_not_hardcoded_ids() -> None:
    client = MagicMock()
    client.discover_lahore_locations.return_value = [_location_with_sensors()]
    window = BootstrapWindow(
        start=datetime(2026, 5, 1, tzinfo=UTC),
        end=datetime(2026, 5, 8, tzinfo=UTC),
    )
    settings = MagicMock()
    settings.lahore_latitude = 31.5204
    settings.lahore_longitude = 74.3587

    plan = build_bootstrap_plan(
        client=client,
        settings=settings,
        window=window,
        aq_chunk_days=3,
    )
    assert plan.target_tables[0].startswith("raw.")
    assert len(plan.discovery.target_sensors) == 2
    assert plan.estimated_weather_days >= 1
    assert plan.mode == "full"
    assert plan.data_provenance["air_quality"] == "openaq_measured"
    assert plan.data_provenance["weather"] == "open_meteo_model_historical"
    # No hard-coded sensor list in plan — only discovered IDs
    assert {s.sensor_id for s in plan.discovery.target_sensors} == {501, 503}


def test_iter_chunks_covers_window() -> None:
    window = BootstrapWindow(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 7, tzinfo=UTC),
    )
    chunks = iter_chunks(window, chunk_days=3)
    assert chunks[0].start == window.start
    assert chunks[-1].end == window.end
    # 1 Jan → 7 Jan with 3-day chunks → [1–4), [4–7]
    assert len(chunks) == 2
