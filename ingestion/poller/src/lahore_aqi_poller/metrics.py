"""In-process counters for poller health and throughput."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class PollMetrics:
    """Cumulative metrics for the polling service."""

    successful_polls: int = 0
    failed_polls: int = 0
    records_received: int = 0
    records_rejected: int = 0
    records_published: int = 0
    by_source: dict[str, dict[str, int]] = field(default_factory=dict)

    def _source_bucket(self, source: str) -> dict[str, int]:
        if source not in self.by_source:
            self.by_source[source] = {
                "successful_polls": 0,
                "failed_polls": 0,
                "records_received": 0,
                "records_rejected": 0,
                "records_published": 0,
            }
        return self.by_source[source]

    def mark_success(self, source: str) -> None:
        self.successful_polls += 1
        self._source_bucket(source)["successful_polls"] += 1

    def mark_failure(self, source: str) -> None:
        self.failed_polls += 1
        self._source_bucket(source)["failed_polls"] += 1

    def add_received(self, source: str, count: int) -> None:
        self.records_received += count
        self._source_bucket(source)["records_received"] += count

    def add_rejected(self, source: str, count: int = 1) -> None:
        self.records_rejected += count
        self._source_bucket(source)["records_rejected"] += count

    def add_published(self, source: str, count: int = 1) -> None:
        self.records_published += count
        self._source_bucket(source)["records_published"] += count

    def as_dict(self) -> dict[str, object]:
        return asdict(self)
