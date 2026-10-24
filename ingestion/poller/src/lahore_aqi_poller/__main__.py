"""CLI entrypoint: ``python -m lahore_aqi_poller`` / ``lahore-aqi-poller``."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from lahore_air_quality.config import get_settings
from lahore_aqi_poller.logging_config import configure_logging
from lahore_aqi_poller.producers import NoOpPublisher, RedpandaPublisher
from lahore_aqi_poller.service import PollerService

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lahore-aqi-poller",
        description=(
            "Poll OpenAQ and Open-Meteo for Lahore air-quality and weather data, "
            "then publish JSON events to Redpanda (Kafka protocol)."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single poll cycle and exit (overrides POLL_ONCE).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Poll interval in seconds (overrides POLL_INTERVAL_SECONDS).",
    )
    parser.add_argument(
        "--no-redpanda",
        action="store_true",
        help="Dry-run: do not publish to Redpanda (NoOpPublisher).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the polling service. Configuration comes from environment / .env."""
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    get_settings.cache_clear()
    settings = get_settings()

    configure_logging(level=settings.log_level, json_logs=settings.log_json)

    once = bool(args.once or settings.poll_once)
    interval = args.interval if args.interval is not None else settings.poll_interval_seconds

    if args.no_redpanda:
        publisher = NoOpPublisher()
        logger.warning("publisher_noop", extra={"reason": "--no-redpanda"})
    else:
        publisher = RedpandaPublisher.from_settings(settings)
        health = publisher.health_check()
        logger.info(
            "redpanda_health",
            extra={
                "healthy": health.healthy,
                "health_message": health.message,
                "brokers": health.brokers,
            },
        )

    service = PollerService.from_settings(
        settings,
        publisher=publisher,
        interval_seconds=interval,
    )

    logger.info(
        "cli_start",
        extra={
            "once": once,
            "interval_seconds": interval,
            "poll_enable_openaq": settings.poll_enable_openaq,
            "poll_enable_openmeteo": settings.poll_enable_openmeteo,
            "redpanda_enabled": not args.no_redpanda,
        },
    )
    metrics = service.run(once=once)
    logger.info("cli_exit", extra={"metrics": metrics.as_dict()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
