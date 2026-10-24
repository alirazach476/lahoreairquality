"""Publisher protocol for ingestion events."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lahore_aqi_poller.events import IngestionEvent


@runtime_checkable
class EventPublisher(Protocol):
    """Destination for poller output events."""

    def publish(self, event: IngestionEvent) -> None:
        """Accept one event. Must not write to PostgreSQL."""
        ...


class NoOpPublisher:
    """Acknowledges events without sending them anywhere (tests / dry-run)."""

    def publish(self, event: IngestionEvent) -> None:
        return None

    def close(self) -> None:
        return None


class RecordingPublisher:
    """In-memory publisher for tests."""

    def __init__(self) -> None:
        self.events: list[IngestionEvent] = []

    def publish(self, event: IngestionEvent) -> None:
        self.events.append(event)

    def close(self) -> None:
        return None
