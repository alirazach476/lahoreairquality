"""Failure-scenario catalog and pipeline status (portfolio / operator visibility)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response, status

from lahore_air_quality.resilience import (
    build_pipeline_status,
    get_scenario,
    list_scenarios,
)
from lahore_air_quality.resilience.scenarios import ScenarioId

router = APIRouter(tags=["resilience"])


@router.get(
    "/resilience/scenarios",
    summary="Documented failure scenarios and expected recovery behavior",
)
def resilience_scenarios() -> dict[str, Any]:
    scenarios = [s.as_dict() for s in list_scenarios()]
    return {"count": len(scenarios), "scenarios": scenarios}


@router.get(
    "/resilience/scenarios/{scenario_id}",
    summary="One failure scenario contract",
)
def resilience_scenario(scenario_id: ScenarioId) -> dict[str, Any]:
    return get_scenario(scenario_id).as_dict()


@router.get(
    "/resilience/status",
    summary="Pipeline dependency status plus scenario catalog size",
)
def resilience_status(request: Request, response: Response) -> dict[str, Any]:
    checker = getattr(request.app.state, "health_checker", None)
    snapshot = build_pipeline_status(
        database_checker=checker if callable(checker) else None,
    )
    if not snapshot.overall_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return snapshot.as_dict()
