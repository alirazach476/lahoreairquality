"""Fixtures for ingestion client tests (mocked HTTP by default)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from lahore_aqi_poller.clients.openaq import OpenAQClient
from lahore_aqi_poller.clients.openmeteo import OpenMeteoClient

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def openaq_client_factory() -> Callable[..., OpenAQClient]:
    """Build an OpenAQ client bound to an httpx MockTransport handler."""

    def _factory(handler: Handler, **kwargs: Any) -> OpenAQClient:
        transport = httpx.MockTransport(handler)
        return OpenAQClient(
            api_key=kwargs.pop("api_key", "test-key-not-real"),
            base_url=kwargs.pop("base_url", "https://api.openaq.org"),
            transport=transport,
            min_request_interval_seconds=kwargs.pop("min_request_interval_seconds", 0.0),
            max_retries=kwargs.pop("max_retries", 2),
            **kwargs,
        )

    return _factory


@pytest.fixture
def openmeteo_client_factory() -> Callable[..., OpenMeteoClient]:
    """Build an Open-Meteo client bound to an httpx MockTransport handler."""

    def _factory(handler: Handler, **kwargs: Any) -> OpenMeteoClient:
        transport = httpx.MockTransport(handler)
        return OpenMeteoClient(
            latitude=kwargs.pop("latitude", 31.5204),
            longitude=kwargs.pop("longitude", 74.3587),
            forecast_base_url=kwargs.pop("forecast_base_url", "https://api.open-meteo.com"),
            archive_base_url=kwargs.pop("archive_base_url", "https://archive-api.open-meteo.com"),
            transport=transport,
            max_retries=kwargs.pop("max_retries", 2),
            **kwargs,
        )

    return _factory
