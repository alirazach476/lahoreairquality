"""Weather historical persist ceiling (completed UTC hour) — no DB writes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from ingestion.bootstrap_history.plan import build_bootstrap_plan
from ingestion.bootstrap_history.runner import (
    execute_bootstrap,
    filter_weather_through_persist_end,
)
from ingestion.bootstrap_history.settings import (
    BootstrapWindow,
    as_utc,
    completed_utc_hour,
    effective_weather_persist_end,
)

from lahore_aqi_poller.clients.openmeteo.models import (
    NormalizedWeatherObservation,
    WeatherObservationBundle,
)


def _wx_bundle(observed_at: datetime) -> WeatherObservationBundle:
    return WeatherObservationBundle(
        observation=NormalizedWeatherObservation(
            observed_at=observed_at,
            latitude=31.52,
            longitude=74.36,
            temperature_c=25.0,
            relative_humidity_pct=50.0,
            precipitation_mm=0.0,
            wind_speed_ms=1.0,
            wind_direction_deg=180.0,
            pressure_hpa=1000.0,
            source="open-meteo",
            raw_record_id=f"wx-{observed_at.isoformat()}",
        ),
        raw_payload={"time": observed_at.isoformat()},
    )


def _settings() -> MagicMock:
    settings = MagicMock()
    settings.lahore_latitude = 31.5204
    settings.lahore_longitude = 74.3587
    settings.s3_endpoint_url = "http://localhost:9000"
    settings.s3_bucket = "test"
    settings.aws_access_key_id = MagicMock()
    settings.aws_access_key_id.get_secret_value.return_value = "x"
    settings.aws_secret_access_key = MagicMock()
    settings.aws_secret_access_key.get_secret_value.return_value = "y"
    settings.aws_region = "us-east-1"
    return settings


def test_as_utc_naive_and_aware() -> None:
    naive = datetime(2026, 10, 24, 8, 30, 0)
    aware = as_utc(naive)
    assert aware.tzinfo is UTC
    assert aware.hour == 8

    pkt = timezone(timedelta(hours=5))
    local = datetime(2026, 10, 24, 13, 30, tzinfo=pkt)  # 08:30 UTC
    assert as_utc(local) == datetime(2026, 10, 24, 8, 30, tzinfo=UTC)


def test_completed_utc_hour_truncates_minutes() -> None:
    now = datetime(2026, 10, 24, 8, 47, 58, tzinfo=UTC)
    assert completed_utc_hour(now=now) == datetime(2026, 10, 24, 8, 0, tzinfo=UTC)


def test_effective_persist_end_caps_at_completed_hour() -> None:
    now = datetime(2026, 10, 24, 8, 47, tzinfo=UTC)
    requested = datetime(2026, 10, 24, 8, 0, tzinfo=UTC)
    assert effective_weather_persist_end(requested, now=now) == requested

    # Requested end already at completed hour when window built mid-hour.
    past_end = datetime(2026, 5, 3, 0, 0, tzinfo=UTC)
    assert effective_weather_persist_end(past_end, now=now) == past_end


def test_filter_same_day_archive_excludes_future_hours() -> None:
    """Archive returned full calendar day; hours after completed UTC hour drop."""
    now = datetime(2026, 10, 24, 8, 47, tzinfo=UTC)
    persist_end = effective_weather_persist_end(datetime(2026, 10, 24, 8, 0, tzinfo=UTC), now=now)
    assert persist_end == datetime(2026, 10, 24, 8, 0, tzinfo=UTC)

    hours = [_wx_bundle(datetime(2026, 10, 24, h, tzinfo=UTC)) for h in range(24)]
    eligible, skipped = filter_weather_through_persist_end(hours, persist_end=persist_end)
    assert len(eligible) == 9  # 00..08 inclusive
    assert len(skipped) == 15  # 09..23
    assert eligible[-1].observation.observed_at == datetime(2026, 10, 24, 8, tzinfo=UTC)
    assert skipped[0].observation.observed_at == datetime(2026, 10, 24, 9, tzinfo=UTC)


def test_filter_fully_past_dates_keep_all() -> None:
    now = datetime(2026, 10, 24, 8, 47, tzinfo=UTC)
    persist_end = effective_weather_persist_end(datetime(2026, 5, 3, 0, 0, tzinfo=UTC), now=now)
    hours = [
        _wx_bundle(datetime(2026, 5, 1, 12, tzinfo=UTC)),
        _wx_bundle(datetime(2026, 5, 2, 23, tzinfo=UTC)),
        _wx_bundle(datetime(2026, 5, 3, 0, tzinfo=UTC)),
    ]
    eligible, skipped = filter_weather_through_persist_end(hours, persist_end=persist_end)
    assert len(eligible) == 3
    assert skipped == []


def test_utc_boundary_exact_completed_hour_included() -> None:
    persist_end = datetime(2026, 10, 24, 8, 0, tzinfo=UTC)
    at_boundary = _wx_bundle(persist_end)
    after = _wx_bundle(persist_end + timedelta(hours=1))
    eligible, skipped = filter_weather_through_persist_end(
        [at_boundary, after], persist_end=persist_end
    )
    assert eligible == [at_boundary]
    assert skipped == [after]


def test_plan_distinguishes_requested_vs_persist_end() -> None:
    window = BootstrapWindow(
        start=datetime(2026, 10, 17, 8, 0, tzinfo=UTC),
        end=datetime(2026, 10, 24, 8, 0, tzinfo=UTC),
    )
    with patch(
        "ingestion.bootstrap_history.plan.effective_weather_persist_end",
        return_value=datetime(2026, 10, 24, 8, 0, tzinfo=UTC),
    ):
        plan = build_bootstrap_plan(
            settings=_settings(),
            window=window,
            weather_only=True,
        )
    payload = plan.as_dict()
    assert payload["requested_window"]["end_utc"] == "2026-10-24T08:00:00+00:00"
    assert payload["weather_archive_calendar_dates"] == {
        "start_date": "2026-10-17",
        "end_date": "2026-10-24",
    }
    assert payload["weather_persist_end_utc"] == "2026-10-24T08:00:00+00:00"
    assert any("persist" in n.lower() for n in plan.resource_notes)


def test_execute_skips_future_hours_before_persist() -> None:
    window = BootstrapWindow(
        start=datetime(2026, 10, 24, 0, 0, tzinfo=UTC),
        end=datetime(2026, 10, 24, 8, 0, tzinfo=UTC),
    )
    plan = build_bootstrap_plan(settings=_settings(), window=window, weather_only=True)
    now = datetime(2026, 10, 24, 8, 47, tzinfo=UTC)
    meteo = MagicMock()
    meteo.fetch_historical.return_value = [
        _wx_bundle(datetime(2026, 10, 24, h, tzinfo=UTC)) for h in range(24)
    ]

    processor = MagicMock()
    processor.process.return_value = MagicMock(
        status="processed", event_id="e", detail=None, failed_stage=None
    )

    with (
        patch(
            "ingestion.bootstrap_history.runner.build_event_processor",
            return_value=(processor, "postgres_only"),
        ),
        patch("ingestion.bootstrap_history.runner.persist_event") as persist,
    ):
        result = execute_bootstrap(
            plan,
            session_factory=MagicMock(),
            settings=_settings(),
            openmeteo_client=meteo,
            now=now,
        )

    assert result.weather_observations_fetched == 24
    assert result.weather_observations_eligible == 9
    assert result.weather_observations_skipped_future == 15
    assert result.weather_persist_end_utc == "2026-10-24T08:00:00+00:00"
    assert persist.call_count == 9
    meteo.fetch_historical.assert_called_once_with(
        start_date=window.start.date(),
        end_date=window.end.date(),
        latitude=31.5204,
        longitude=74.3587,
    )


def test_execute_past_window_persists_all_hours() -> None:
    window = BootstrapWindow(
        start=datetime(2026, 5, 1, tzinfo=UTC),
        end=datetime(2026, 5, 3, tzinfo=UTC),
    )
    plan = build_bootstrap_plan(settings=_settings(), window=window, weather_only=True)
    now = datetime(2026, 10, 24, 8, 47, tzinfo=UTC)
    meteo = MagicMock()
    meteo.fetch_historical.return_value = [
        _wx_bundle(datetime(2026, 5, 1, 12, tzinfo=UTC)),
        _wx_bundle(datetime(2026, 5, 2, 18, tzinfo=UTC)),
    ]

    with (
        patch(
            "ingestion.bootstrap_history.runner.build_event_processor",
            return_value=(MagicMock(), "postgres_only"),
        ),
        patch("ingestion.bootstrap_history.runner.persist_event") as persist,
    ):
        result = execute_bootstrap(
            plan,
            session_factory=MagicMock(),
            settings=_settings(),
            openmeteo_client=meteo,
            now=now,
        )

    assert result.weather_observations_fetched == 2
    assert result.weather_observations_eligible == 2
    assert result.weather_observations_skipped_future == 0
    assert persist.call_count == 2
