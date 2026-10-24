"""Inference-specific errors (clear failure modes for callers)."""

from __future__ import annotations


class InferenceError(Exception):
    """Base class for inference failures."""


class ModelNotFoundError(InferenceError):
    """No usable trained model artifact / metadata was found."""


class InputValidationError(InferenceError):
    """Observation frame failed schema or value checks."""


class InsufficientHistoryError(InferenceError):
    """Not enough chronological history to build training-parity features."""
