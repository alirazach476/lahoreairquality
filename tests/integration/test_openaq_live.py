"""Optional live OpenAQ API integration tests.

Not run by default. See docs/testing.md.
"""

from __future__ import annotations

import pytest

from lahore_air_quality.config import Settings
from lahore_aqi_poller.clients.openaq import OpenAQClient

pytestmark = pytest.mark.integration


def test_live_discover_lahore_locations(live_settings: Settings, openaq_api_key: str) -> None:
    with OpenAQClient(
        api_key=openaq_api_key,
        base_url=live_settings.openaq_base_url,
        min_request_interval_seconds=1.05,
    ) as client:
        locations = client.discover_lahore_locations()

    assert isinstance(locations, list)
    # Coverage in OpenAQ can change; discovery must succeed even if empty.
    for location in locations:
        assert location.id > 0
        assert location.sensors is not None


def test_live_fetch_recent_when_locations_exist(
    live_settings: Settings, openaq_api_key: str
) -> None:
    with OpenAQClient(
        api_key=openaq_api_key,
        base_url=live_settings.openaq_base_url,
        min_request_interval_seconds=1.05,
    ) as client:
        locations = client.discover_lahore_locations()
        if not locations:
            pytest.skip("No Lahore locations currently available in OpenAQ")
        bundles = client.fetch_recent_measurements(locations=locations[:1])

    assert isinstance(bundles, list)
    for bundle in bundles:
        assert bundle.observation.source == "openaq"
        assert bundle.raw_payload
