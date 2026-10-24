"""CLI: ``python -m lahore_aqi_consumer`` / ``lahore-aqi-consumer``."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from lahore_air_quality.config import get_settings
from lahore_air_quality.db.session import get_session_factory
from lahore_aqi_consumer.logging_config import configure_logging
from lahore_aqi_consumer.processing import EventProcessor
from lahore_aqi_consumer.service import ConsumerService
from lahore_aqi_consumer.storage.postgres import PostgresObservationWriter
from lahore_aqi_consumer.storage.s3 import S3ObjectStore

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lahore-aqi-consumer",
        description=(
            "Consume Redpanda air-quality and weather events, archive raw JSON to "
            "S3/MinIO, and upsert normalized rows into PostgreSQL."
        ),
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=None,
        help="Stop after N consumed messages (useful for smoke tests).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    get_settings.cache_clear()
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)

    store = S3ObjectStore.from_settings(settings)
    try:
        store.ensure_bucket()
    except Exception as exc:
        logger.error(
            "s3_bucket_ensure_failed",
            extra={"error_type": type(exc).__name__, "bucket": settings.s3_bucket},
        )
        # Continue — put_object may still work if bucket exists.

    processor = EventProcessor(
        object_store=store,
        postgres_writer=PostgresObservationWriter(get_session_factory()),
    )
    service = ConsumerService.from_settings(settings, processor=processor)

    logger.info(
        "cli_start",
        extra={
            "brokers": settings.redpanda_brokers,
            "group": settings.redpanda_consumer_group,
            "topics": [
                settings.redpanda_topic_air_quality,
                settings.redpanda_topic_weather,
            ],
            "s3_bucket": settings.s3_bucket,
            "max_messages": args.max_messages,
        },
    )
    metrics = service.run(max_messages=args.max_messages)
    logger.info("cli_exit", extra={"metrics": metrics.as_dict()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
