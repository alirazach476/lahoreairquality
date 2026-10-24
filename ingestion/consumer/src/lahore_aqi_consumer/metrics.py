"""In-process counters for the Redpanda consumer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ConsumerMetrics:
    """Cumulative processing metrics."""

    consumed: int = 0
    processed: int = 0
    rejected: int = 0
    duplicate: int = 0
    failed: int = 0
    by_source: dict[str, dict[str, int]] = field(default_factory=dict)

    def _bucket(self, source: str) -> dict[str, int]:
        if source not in self.by_source:
            self.by_source[source] = {
                "consumed": 0,
                "processed": 0,
                "rejected": 0,
                "duplicate": 0,
                "failed": 0,
            }
        return self.by_source[source]

    def mark_consumed(self, source: str = "unknown") -> None:
        self.consumed += 1
        self._bucket(source)["consumed"] += 1

    def mark_processed(self, source: str) -> None:
        self.processed += 1
        self._bucket(source)["processed"] += 1

    def mark_rejected(self, source: str = "unknown") -> None:
        self.rejected += 1
        self._bucket(source)["rejected"] += 1

    def mark_duplicate(self, source: str) -> None:
        self.duplicate += 1
        self._bucket(source)["duplicate"] += 1

    def mark_failed(self, source: str = "unknown") -> None:
        self.failed += 1
        self._bucket(source)["failed"] += 1

    def as_dict(self) -> dict[str, object]:
        return asdict(self)
