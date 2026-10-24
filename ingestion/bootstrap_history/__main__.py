"""``python -m ingestion.bootstrap_history`` — plan or execute historical import."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime

from ingestion.bootstrap_history.plan import build_bootstrap_plan
from ingestion.bootstrap_history.runner import execute_bootstrap
from ingestion.bootstrap_history.settings import (
    DEFAULT_LOOKBACK_DAYS,
    BootstrapWindow,
)
from lahore_air_quality.config import get_settings
from lahore_air_quality.db.health import check_database_health
from lahore_air_quality.db.session import get_session_factory
from lahore_air_quality.quality.load import count_air_quality_rows, count_weather_rows


def _parse_dt(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap historical Lahore data into existing raw tables. "
            "Default: plan only (no writes). "
            "Use --weather-only to import Open-Meteo archive weather without OpenAQ."
        )
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Print the import plan only (default if --execute omitted)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the import after building the same plan",
    )
    parser.add_argument(
        "--weather-only",
        action="store_true",
        help=(
            "Skip OpenAQ (no OPENAQ_API_KEY required). Import only Open-Meteo "
            "historical weather (model/reanalysis — not ground stations)."
        ),
    )
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--from", dest="date_from", default=None, help="UTC start ISO")
    parser.add_argument("--to", dest="date_to", default=None, help="UTC end ISO")
    parser.add_argument("--chunk-days", type=int, default=3)
    parser.add_argument("--radius-m", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--require-object-store",
        action="store_true",
        help="Fail if MinIO/S3 is unreachable (default: Postgres-only fallback)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    window = None
    if args.date_from or args.date_to:
        if not (args.date_from and args.date_to):
            print("error: --from and --to must be provided together", file=sys.stderr)
            return 2
        window = BootstrapWindow(start=_parse_dt(args.date_from), end=_parse_dt(args.date_to))

    try:
        plan = build_bootstrap_plan(
            lookback_days=args.days,
            window=window,
            aq_chunk_days=args.chunk_days,
            radius_m=args.radius_m,
            weather_only=args.weather_only,
        )
    except Exception as exc:  # noqa: BLE001
        # Avoid dumping exception args that might echo secrets from misconfigured env.
        print(
            f"error: failed to build plan: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    if not args.execute:
        _print_plan(plan, as_json=args.json)
        print(
            "\nNo data was written. Re-run with --execute after reviewing this plan.",
            file=sys.stderr,
        )
        return 0

    health = check_database_health()
    if not health.healthy:
        print(f"error: database unavailable: {health.message}", file=sys.stderr)
        return 2

    session_factory = get_session_factory()
    pre_session = session_factory()
    try:
        aq_before = count_air_quality_rows(pre_session)
        wx_before = count_weather_rows(pre_session)
    finally:
        pre_session.close()

    result = execute_bootstrap(
        plan,
        session_factory=session_factory,
        settings=get_settings(),
        require_object_store=args.require_object_store,
    )

    post_session = session_factory()
    try:
        aq_after = count_air_quality_rows(post_session)
        wx_after = count_weather_rows(post_session)
    finally:
        post_session.close()

    verification = {
        "database_healthy": True,
        "air_quality_rows_before": aq_before,
        "air_quality_rows_after": aq_after,
        "air_quality_rows_delta": aq_after - aq_before,
        "weather_rows_before": wx_before,
        "weather_rows_after": wx_after,
        "weather_rows_delta": wx_after - wx_before,
    }
    payload = result.as_dict()
    payload["database_verification"] = verification

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        _print_plan(plan, as_json=False)
        print("\n=== execution ===")
        print(f"storage_mode: {result.storage_mode}")
        print(f"aq_fetched: {result.aq_observations_fetched}")
        print(f"aq_skipped_outside_window: {result.aq_observations_skipped_outside_window}")
        print(f"aq_persist: {result.air_quality.as_dict()}")
        print(f"weather_fetched: {result.weather_observations_fetched}")
        print(f"weather_eligible: {result.weather_observations_eligible}")
        print(f"weather_skipped_future: {result.weather_observations_skipped_future}")
        print(f"weather_persist_end_utc: {result.weather_persist_end_utc}")
        print(f"weather_persist: {result.weather.as_dict()}")
        print(f"empty_sensor_chunks: {result.empty_sensor_chunks}")
        print(f"errors: {result.errors}")
        print(f"database_verification: {verification}")
        for note in result.notes:
            print(f"note: {note}")

    if result.errors and (
        (plan.include_air_quality and aq_after == aq_before and wx_after == wx_before)
        or (not plan.include_air_quality and wx_after == wx_before)
    ):
        return 1
    return 0


def _print_plan(plan: object, *, as_json: bool) -> None:
    from ingestion.bootstrap_history.plan import BootstrapPlan

    assert isinstance(plan, BootstrapPlan)
    if as_json:
        print(json.dumps(plan.as_dict(), indent=2, default=str))
        return
    print("=== bootstrap plan (no writes in --plan mode) ===")
    print(f"mode: {plan.mode}")
    print(f"requested_window: {plan.window.as_dict()}")
    print(f"weather_archive_calendar_dates: {plan.weather_archive_calendar_dates()}")
    print(f"weather_persist_end_utc: {plan.weather_persist_end_utc()}")
    print(
        f"weather_point: lat={plan.weather_latitude} lon={plan.weather_longitude} "
        "(Open-Meteo model/reanalysis historical — not ground stations)"
    )
    print(f"target_tables: {list(plan.target_tables)}")
    print(f"object_storage_prefix: {plan.object_storage_prefix}")
    if plan.include_air_quality:
        print(f"locations_found: {plan.discovery.locations_found}")
        print(f"sensors_total: {plan.discovery.sensors_total}")
        print(f"pm_target_sensors: {len(plan.discovery.target_sensors)}")
        print(f"pollutants_available: {plan.discovery.pollutants_available}")
        for sensor in plan.discovery.target_sensors:
            print(f"  sensor: {sensor.as_dict()}")
        print(f"estimated_aq_sensor_chunks: {plan.estimated_aq_sensor_chunks}")
    else:
        print("air_quality: skipped (weather_only)")
    print(f"estimated_weather_days: {plan.estimated_weather_days}")
    for note in plan.resource_notes:
        print(f"resource: {note}")
    for attr in plan.attribution:
        print(f"attribution: {attr}")
    for warning in plan.warnings:
        print(f"warning: {warning}")
    for note in plan.discovery.notes:
        print(f"discovery: {note}")


if __name__ == "__main__":
    raise SystemExit(main())
