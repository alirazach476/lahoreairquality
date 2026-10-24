"""Lightweight pipeline status snapshot for operators and tests."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

from lahore_air_quality.db.health import DatabaseHealth, check_database_health
from lahore_air_quality.resilience.scenarios import list_scenarios

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ComponentStatus:
    name: str
    healthy: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PipelineStatusSnapshot:
    generated_at: datetime
    overall_healthy: bool
    components: tuple[ComponentStatus, ...]
    scenario_catalog_size: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "overall_healthy": self.overall_healthy,
            "components": [c.as_dict() for c in self.components],
            "scenario_catalog_size": self.scenario_catalog_size,
            "scenarios": [s.as_dict() for s in list_scenarios()],
        }


def build_pipeline_status(
    *,
    database_checker: Callable[[], DatabaseHealth] | None = None,
    redpanda_probe: Callable[[], ComponentStatus] | None = None,
    object_store_probe: Callable[[], ComponentStatus] | None = None,
) -> PipelineStatusSnapshot:
    """Assemble dependency status. Probes are injectable for unit tests.

    Always includes PostgreSQL. Redpanda / object storage are optional probes
    so the API can expose DB health without requiring Kafka credentials.
    """
    checker = database_checker or check_database_health
    db = checker()
    components: list[ComponentStatus] = [
        ComponentStatus(
            name="postgres",
            healthy=db.healthy,
            message=db.message,
            details=dict(db.details or {}),
        )
    ]
    if redpanda_probe is not None:
        components.append(redpanda_probe())
    if object_store_probe is not None:
        components.append(object_store_probe())

    overall = all(c.healthy for c in components)
    if not overall:
        logger.warning(
            "pipeline_status_degraded",
            extra={
                "unhealthy": [c.name for c in components if not c.healthy],
            },
        )
    else:
        logger.info("pipeline_status_ok", extra={"components": [c.name for c in components]})

    return PipelineStatusSnapshot(
        generated_at=datetime.now(tz=UTC),
        overall_healthy=overall,
        components=tuple(components),
        scenario_catalog_size=len(list_scenarios()),
    )
