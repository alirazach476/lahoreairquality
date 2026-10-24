"""Structured, monitoring-friendly logging helpers for Dagster assets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dagster import AssetExecutionContext, OpExecutionContext


def log_stage(
    context: AssetExecutionContext | OpExecutionContext,
    event: str,
    *,
    stage: str,
    **fields: Any,
) -> None:
    """Emit a single structured log line Dagster UI / log aggregators can parse."""
    payload = {"event": event, "stage": stage, **fields}
    # Prefer JSON-ish key=value for grep-friendly operator logs.
    rendered = " ".join(f"{key}={_fmt(value)}" for key, value in payload.items())
    context.log.info(rendered)


def log_metrics(
    context: AssetExecutionContext | OpExecutionContext,
    *,
    stage: str,
    metrics: Mapping[str, Any],
) -> None:
    log_stage(context, "stage_metrics", stage=stage, **dict(metrics))


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    text = str(value)
    if " " in text or "=" in text:
        return f'"{text}"'
    return text
