"""Redpanda consumer: archive raw JSON to S3 and load PostgreSQL."""

from lahore_aqi_consumer.processing import EventProcessor, ProcessResult
from lahore_aqi_consumer.service import ConsumerService

__version__ = "0.1.0"

__all__ = ["ConsumerService", "EventProcessor", "ProcessResult", "__version__"]
