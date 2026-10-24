"""Poller package: fetch Lahore AQ/weather and emit ingestion events."""

from lahore_aqi_poller.service import PollerService

__version__ = "0.1.0"

__all__ = ["PollerService", "__version__"]
