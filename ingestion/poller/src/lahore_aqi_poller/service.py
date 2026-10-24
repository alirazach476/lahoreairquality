"""Periodic Lahore air-quality + weather polling service.

Uses existing OpenAQ / Open-Meteo clients and an
:class:`~lahore_aqi_poller.producers.base.EventPublisher` (typically
:class:`~lahore_aqi_poller.producers.redpanda.RedpandaPublisher`).
Does **not** write to PostgreSQL.
"""

from __future__ import annotations

import logging
import signal
import threading
from datetime import UTC, datetime
from types import FrameType
from typing import Any

from lahore_aqi_poller.clients.openaq import OpenAQClient
from lahore_aqi_poller.clients.openaq.exceptions import OpenAQConfigError, OpenAQError
from lahore_aqi_poller.clients.openmeteo import OpenMeteoClient
from lahore_aqi_poller.clients.openmeteo.exceptions import OpenMeteoError
from lahore_aqi_poller.metrics import PollMetrics
from lahore_aqi_poller.producers import EventPublisher, NoOpPublisher
from lahore_aqi_poller.transforms import (
    air_quality_bundle_to_event,
    weather_bundle_to_event,
)

logger = logging.getLogger(__name__)


class PollerService:
    """Poll OpenAQ and Open-Meteo on an interval with graceful shutdown."""

    def __init__(
        self,
        *,
        openaq_client: OpenAQClient | None,
        openmeteo_client: OpenMeteoClient | None,
        publisher: EventPublisher | None = None,
        interval_seconds: float = 300.0,
        enable_openaq: bool = True,
        enable_openmeteo: bool = True,
        metrics: PollMetrics | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        self._openaq = openaq_client
        self._openmeteo = openmeteo_client
        self._publisher: EventPublisher = publisher or NoOpPublisher()
        self._interval_seconds = interval_seconds
        self._enable_openaq = enable_openaq
        self._enable_openmeteo = enable_openmeteo
        self.metrics = metrics or PollMetrics()
        self._stop = threading.Event()
        self._poll_lock = threading.Lock()

    @classmethod
    def from_settings(
        cls,
        settings: Any | None = None,
        *,
        publisher: EventPublisher | None = None,
        interval_seconds: float | None = None,
    ) -> PollerService:
        """Build a service from :class:`lahore_air_quality.config.Settings`."""
        if settings is None:
            from lahore_air_quality.config import get_settings

            settings = get_settings()

        openaq_client: OpenAQClient | None = None
        if settings.poll_enable_openaq:
            try:
                openaq_client = OpenAQClient.from_settings(settings)
            except OpenAQConfigError as exc:
                logger.warning(
                    "openaq_client_unavailable",
                    extra={"error": str(exc)},
                )

        openmeteo_client: OpenMeteoClient | None = None
        if settings.poll_enable_openmeteo:
            openmeteo_client = OpenMeteoClient.from_settings(settings)

        return cls(
            openaq_client=openaq_client,
            openmeteo_client=openmeteo_client,
            publisher=publisher,
            interval_seconds=(
                interval_seconds if interval_seconds is not None else settings.poll_interval_seconds
            ),
            enable_openaq=settings.poll_enable_openaq,
            enable_openmeteo=settings.poll_enable_openmeteo,
        )

    def request_shutdown(self, *_args: object) -> None:
        """Signal the run loop to stop after the current wait/poll."""
        logger.info("shutdown_requested")
        self._stop.set()

    def install_signal_handlers(self) -> None:
        """Register SIGINT/SIGTERM handlers for graceful shutdown."""

        def _handler(signum: int, _frame: FrameType | None) -> None:
            logger.info("signal_received", extra={"signum": signum})
            self.request_shutdown()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                # Signals may be unavailable (non-main thread / Windows edge cases).
                logger.debug("signal_handler_not_installed", extra={"signum": int(sig)})

    def run(self, *, once: bool = False) -> PollMetrics:
        """Run poll cycles until shutdown or a single cycle when ``once`` is true."""
        self.install_signal_handlers()
        logger.info(
            "poller_started",
            extra={
                "interval_seconds": self._interval_seconds,
                "enable_openaq": self._enable_openaq,
                "enable_openmeteo": self._enable_openmeteo,
                "once": once,
            },
        )

        while not self._stop.is_set():
            self.poll_once()
            if once:
                break
            # Wait for interval or early wake on shutdown.
            if self._stop.wait(timeout=self._interval_seconds):
                break

        self._close_clients()
        logger.info("poller_stopped", extra={"metrics": self.metrics.as_dict()})
        return self.metrics

    def poll_once(self) -> PollMetrics:
        """Execute one poll cycle for enabled sources (isolated failures)."""
        with self._poll_lock:
            ingested_at = datetime.now(tz=UTC)
            logger.info("poll_cycle_started", extra={"ingested_at": ingested_at.isoformat()})

            if self._enable_openaq:
                self._poll_air_quality(ingested_at=ingested_at)
            if self._enable_openmeteo:
                self._poll_weather(ingested_at=ingested_at)

            logger.info(
                "poll_cycle_finished",
                extra={"metrics": self.metrics.as_dict()},
            )
            return self.metrics

    def _poll_air_quality(self, *, ingested_at: datetime) -> None:
        source = "openaq"
        if self._openaq is None:
            self.metrics.mark_failure(source)
            logger.error(
                "poll_failed",
                extra={"source": source, "reason": "client_unavailable"},
            )
            return

        try:
            bundles = self._openaq.fetch_recent_measurements()
        except OpenAQError as exc:
            self.metrics.mark_failure(source)
            logger.exception(
                "poll_failed",
                extra={"source": source, "error_type": type(exc).__name__},
            )
            return
        except Exception as exc:
            self.metrics.mark_failure(source)
            logger.exception(
                "poll_failed",
                extra={"source": source, "error_type": type(exc).__name__},
            )
            return

        self.metrics.mark_success(source)
        self.metrics.add_received(source, len(bundles))
        logger.info(
            "poll_success",
            extra={"source": source, "records_received": len(bundles)},
        )

        if not bundles:
            logger.info("poll_empty_result", extra={"source": source})
            return

        for bundle in bundles:
            event = air_quality_bundle_to_event(bundle, ingested_at=ingested_at)
            if event is None:
                self.metrics.add_rejected(source)
                continue
            try:
                self._publisher.publish(event)
            except Exception:
                self.metrics.add_rejected(source)
                logger.exception(
                    "publish_failed",
                    extra={"source": source, "event_id": event.event_id},
                )
                continue
            self.metrics.add_published(source)

    def _poll_weather(self, *, ingested_at: datetime) -> None:
        source = "open-meteo"
        if self._openmeteo is None:
            self.metrics.mark_failure(source)
            logger.error(
                "poll_failed",
                extra={"source": source, "reason": "client_unavailable"},
            )
            return

        try:
            # Current conditions for the application; clients already retry transients.
            current = self._openmeteo.fetch_current()
            bundles = [current] if current is not None else []
        except OpenMeteoError as exc:
            self.metrics.mark_failure(source)
            logger.exception(
                "poll_failed",
                extra={"source": source, "error_type": type(exc).__name__},
            )
            return
        except Exception as exc:
            self.metrics.mark_failure(source)
            logger.exception(
                "poll_failed",
                extra={"source": source, "error_type": type(exc).__name__},
            )
            return

        self.metrics.mark_success(source)
        self.metrics.add_received(source, len(bundles))
        logger.info(
            "poll_success",
            extra={"source": source, "records_received": len(bundles)},
        )

        if not bundles:
            logger.info("poll_empty_result", extra={"source": source})
            return

        for bundle in bundles:
            event = weather_bundle_to_event(bundle, ingested_at=ingested_at)
            if event is None:
                self.metrics.add_rejected(source)
                continue
            try:
                self._publisher.publish(event)
            except Exception:
                self.metrics.add_rejected(source)
                logger.exception(
                    "publish_failed",
                    extra={"source": source, "event_id": event.event_id},
                )
                continue
            self.metrics.add_published(source)

    def _close_clients(self) -> None:
        if self._openaq is not None:
            try:
                self._openaq.close()
            except Exception:
                logger.exception("openaq_client_close_failed")
        if self._openmeteo is not None:
            try:
                self._openmeteo.close()
            except Exception:
                logger.exception("openmeteo_client_close_failed")
        close = getattr(self._publisher, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                logger.exception("publisher_close_failed")
