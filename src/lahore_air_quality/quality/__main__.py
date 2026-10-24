"""CLI: ``python -m lahore_air_quality.quality`` — monitor real Postgres data."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from lahore_air_quality.db.health import check_database_health
from lahore_air_quality.db.session import get_session_factory
from lahore_air_quality.quality.monitor import MonitorResult, run_data_quality_monitor
from lahore_air_quality.quality.thresholds import (
    EXPECTED_AQ_INTERVAL,
    SENSOR_INACTIVE_AFTER,
    STALE_AFTER,
)


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run data-quality monitoring against real PostgreSQL observations "
            "(never synthesizes data)."
        )
    )
    parser.add_argument("--from", dest="observed_from", default=None, help="ISO UTC lower bound")
    parser.add_argument("--to", dest="observed_to", default=None, help="ISO UTC upper bound")
    parser.add_argument("--json", action="store_true", help="Print full JSON result")
    args = parser.parse_args(argv)

    health = check_database_health()
    if not health.healthy:
        result = MonitorResult(
            status="DATABASE_UNAVAILABLE",
            message=health.message,
            generated_at=datetime.now(tz=UTC),
            database={
                "healthy": False,
                "message": health.message,
                "server_version": health.server_version,
            },
            thresholds={
                "stale_after_hours": STALE_AFTER.total_seconds() / 3600.0,
                "sensor_inactive_after_hours": SENSOR_INACTIVE_AFTER.total_seconds() / 3600.0,
                "expected_aq_interval_hours": EXPECTED_AQ_INTERVAL.total_seconds() / 3600.0,
            },
            notes=[
                "Production monitor reads PostgreSQL only — no synthetic fixtures.",
            ],
        )
        _print_result(result, as_json=args.json)
        return 2

    session = get_session_factory()()
    try:
        result = run_data_quality_monitor(
            session,
            observed_from=_parse_dt(args.observed_from),
            observed_to=_parse_dt(args.observed_to),
            database_health=health,
        )
    finally:
        session.close()

    _print_result(result, as_json=args.json)
    if result.status == "OK":
        return 0
    if result.status == "NO_DATA_AVAILABLE":
        return 3
    return 2


def _print_result(result: MonitorResult, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.as_dict(), indent=2, default=str))
        return
    print(f"status: {result.status}")
    print(f"message: {result.message}")
    print(f"table_counts: {result.table_counts}")
    if result.air_quality_report is not None:
        r = result.air_quality_report
        print(f"aq_record_counts: {r.record_counts}")
        print(f"aq_duplicate_counts: {r.duplicate_counts}")
        print(f"aq_null_counts: {r.null_counts}")
        print(f"aq_freshness: {r.freshness}")
        print(f"aq_sensor_activity: {r.sensor_activity}")
        print(f"aq_value_extremes: {r.value_extremes}")
        print(f"aq_missing_intervals: {len(r.missing_intervals)} gap(s)")
        print(f"aq_rule_hits: {r.rule_hit_counts}")
    if result.weather_class_counts:
        print(f"weather_class_counts: {result.weather_class_counts}")
    for note in result.notes:
        print(f"note: {note}")


if __name__ == "__main__":
    raise SystemExit(main())
