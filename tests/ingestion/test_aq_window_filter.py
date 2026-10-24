"""AQ observed_at must fall inside the requested UTC bootstrap window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from ingestion.bootstrap_history.discover import DiscoveredSensor, DiscoveryReport
from ingestion.bootstrap_history.plan import BootstrapPlan
from ingestion.bootstrap_history.runner import execute_bootstrap
from ingestion.bootstrap_history.settings import (
    TARGET_TABLES,
    BootstrapWindow,
    is_within_bootstrap_window,
)

from lahore_aqi_poller.clients.openaq.models import (
    NormalizedAirQualityObservation,
    ObservationBundle,
)


def _window() -> BootstrapWindow:
    return BootstrapWindow(
        start=datetime(2026, 10, 17, 9, 0, tzinfo=UTC),
        end=datetime(2026, 10, 24, 9, 0, tzinfo=UTC),
    )


def test_boundary_end_inclusive() -> None:
    window = _window()
    at_end = window.end
    assert is_within_bootstrap_window(at_end, window) is True


def test_after_boundary_excluded() -> None:
    window = _window()
    after = window.end + timedelta(hours=1)
    assert is_within_bootstrap_window(after, window) is False


def test_before_start_excluded() -> None:
    window = _window()
    before = window.start - timedelta(seconds=1)
    assert is_within_bootstrap_window(before, window) is False


def test_timezone_offset_normalized_to_utc() -> None:
    """PKT (+05:00) 14:00 equals 09:00 UTC — at window end, must be in-window."""
    window = _window()
    pkt = timezone(timedelta(hours=5))
    local_at_end = datetime(2026, 10, 24, 14, 0, tzinfo=pkt)
    assert local_at_end.astimezone(UTC) == window.end
    assert is_within_bootstrap_window(local_at_end, window) is True

    local_after = datetime(2026, 10, 24, 15, 0, tzinfo=pkt)  # 10:00 UTC
    assert is_within_bootstrap_window(local_after, window) is False


def test_naive_timestamp_treated_as_utc() -> None:
    window = _window()
    naive_ok = datetime(2026, 10, 24, 9, 0, 0)  # UTC wall per as_utc
    assert is_within_bootstrap_window(naive_ok, window) is True
    naive_after = datetime(2026, 10, 24, 10, 0, 0)
    assert is_within_bootstrap_window(naive_after, window) is False


def test_none_observed_at_out_of_window() -> None:
    assert is_within_bootstrap_window(None, _window()) is False


def _aq_bundle(*, observed_at: datetime, pollutant: str = "pm25") -> ObservationBundle:
    return ObservationBundle(
        observation=NormalizedAirQualityObservation(
            observation_id=f"meas:{observed_at.isoformat()}",
            station_id="101",
            location_name="Test",
            latitude=Decimal("31.52"),
            longitude=Decimal("74.35"),
            pollutant=pollutant,
            value=Decimal("42.0"),
            unit="µg/m³",
            observed_at=observed_at,
            source="openaq",
            raw_record_id=f"openaq-test-{observed_at.isoformat()}",
        ),
        raw_payload={"value": 42.0},
        location=None,
    )


def _aq_plan(window: BootstrapWindow) -> BootstrapPlan:
    sensor = DiscoveredSensor(
        location_id=101,
        location_name="Test",
        sensor_id=501,
        pollutant="pm25",
        unit="µg/m³",
        location_first=window.start,
        location_last=window.end,
    )
    discovery = DiscoveryReport(
        locations_found=1,
        sensors_total=1,
        target_sensors=[sensor],
        pollutants_available=["pm25"],
    )
    return BootstrapPlan(
        mode="full",
        window=window,
        weather_latitude=31.5204,
        weather_longitude=74.3587,
        target_tables=TARGET_TABLES,
        object_storage_prefix="raw/",
        aq_chunk_days=7,
        discovery=discovery,
        locations=[],
        estimated_aq_sensor_chunks=1,
        estimated_weather_days=7,
        data_provenance={"air_quality": "openaq_measured", "weather": "open_meteo"},
    )


def test_execute_skips_aq_after_window_end() -> None:
    window = _window()
    plan = _aq_plan(window)
    at_end = _aq_bundle(observed_at=window.end)
    after_end = _aq_bundle(observed_at=window.end + timedelta(hours=1))

    openaq = MagicMock()
    openaq.fetch_historical_measurements.return_value = [at_end, after_end]
    meteo = MagicMock()
    meteo.fetch_historical.return_value = []

    settings = MagicMock()
    settings.s3_endpoint_url = "http://localhost:9000"
    settings.s3_bucket = "test"
    settings.aws_access_key_id = MagicMock()
    settings.aws_access_key_id.get_secret_value.return_value = "x"
    settings.aws_secret_access_key = MagicMock()
    settings.aws_secret_access_key.get_secret_value.return_value = "y"
    settings.aws_region = "us-east-1"

    with (
        patch(
            "ingestion.bootstrap_history.runner.build_event_processor",
            return_value=(MagicMock(), "postgres_only"),
        ),
        patch("ingestion.bootstrap_history.runner.persist_event") as persist,
        patch("ingestion.bootstrap_history.runner.location_by_id", return_value={}),
    ):
        result = execute_bootstrap(
            plan,
            session_factory=MagicMock(),
            settings=settings,
            openaq_client=openaq,
            openmeteo_client=meteo,
        )

    assert result.aq_observations_fetched == 2
    assert result.aq_observations_skipped_outside_window == 1
    assert persist.call_count == 1
