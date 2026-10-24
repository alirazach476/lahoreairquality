"""Pipeline failure scenarios, detection, and status helpers.

See ``docs/failure-recovery.md`` for the portfolio/interview narrative.
"""

from lahore_air_quality.resilience.scenarios import (
    FAILURE_SCENARIOS,
    FailureScenario,
    ScenarioId,
    get_scenario,
    list_scenarios,
)
from lahore_air_quality.resilience.status import (
    ComponentStatus,
    PipelineStatusSnapshot,
    build_pipeline_status,
)

__all__ = [
    "FAILURE_SCENARIOS",
    "ComponentStatus",
    "FailureScenario",
    "PipelineStatusSnapshot",
    "ScenarioId",
    "build_pipeline_status",
    "get_scenario",
    "list_scenarios",
]
