"""Gates for optional live external-API integration tests.

These tests are excluded from the default suite (``-m "not integration"``) and
also skip unless ``RUN_EXTERNAL_API_TESTS=1`` is set. They require real network
access and, for OpenAQ, a valid ``OPENAQ_API_KEY``.
"""

from __future__ import annotations

import os

import pytest

from lahore_air_quality.config import Settings, get_settings


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip collected integration tests unless explicitly enabled via env."""
    enabled = os.environ.get("RUN_EXTERNAL_API_TESTS", "").strip() == "1"
    if enabled:
        return
    skip = pytest.mark.skip(
        reason=(
            "Live external API tests disabled. "
            "Set RUN_EXTERNAL_API_TESTS=1 and run: pytest -m integration"
        )
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def live_settings() -> Settings:
    """Load settings for live calls (uses .env when present)."""
    get_settings.cache_clear()
    settings = Settings()
    return settings


@pytest.fixture(scope="session")
def openaq_api_key(live_settings: Settings) -> str:
    key = live_settings.openaq_api_key.get_secret_value().strip()
    if not key:
        pytest.skip("OPENAQ_API_KEY is not set. Add it to .env to run live OpenAQ tests.")
    return key
