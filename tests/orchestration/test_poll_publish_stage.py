"""Unit tests for the poll/publish stage (mocked poller)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from dagster import Failure

from lahore_air_quality.config import Settings
from lahore_aqi_dagster.stages.poll_publish import run_poll_and_publish
from lahore_aqi_poller.metrics import PollMetrics


@dataclass
class _Health:
    healthy: bool
    message: str = "ok"


def _settings() -> Settings:
    return Settings(
        postgres_password="test",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        openaq_api_key="test-key",
    )


def test_poll_publish_success() -> None:
    metrics = PollMetrics()
    metrics.mark_success("openaq")
    metrics.add_published("openaq")
    metrics.mark_success("open-meteo")
    metrics.add_published("open-meteo")

    publisher = MagicMock()
    publisher.health_check.return_value = _Health(True)
    service = MagicMock()
    service.poll_once.return_value = metrics

    result = run_poll_and_publish(
        _settings(),
        publisher_factory=lambda _s: publisher,
        service_factory=lambda _s, publisher=None: service,
    )
    assert result.metrics["records_published"] == 2
    publisher.close.assert_called()


def test_poll_publish_all_failures_raise_temporary_api() -> None:
    metrics = PollMetrics()
    metrics.mark_failure("openaq")
    metrics.mark_failure("open-meteo")

    publisher = MagicMock()
    publisher.health_check.return_value = _Health(True)
    service = MagicMock()
    service.poll_once.return_value = metrics

    with pytest.raises(Failure) as exc_info:
        run_poll_and_publish(
            _settings(),
            publisher_factory=lambda _s: publisher,
            service_factory=lambda _s, publisher=None: service,
        )
    assert exc_info.value.allow_retries is True
