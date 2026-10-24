"""Input validation for inference observation frames."""

from __future__ import annotations

import pandas as pd

from lahore_aqi_ml.features.columns import REQUIRED_INPUT_COLUMNS
from lahore_aqi_ml.features.pipeline import validate_mart_columns
from lahore_aqi_ml.inference.exceptions import InputValidationError


def validate_observations(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate mart-shaped observations; return a cleaned copy.

    Raises ``InputValidationError`` on missing columns, empty frames, or
    non-unique ``(station_id, observed_hour)`` keys.
    """
    if frame is None or not isinstance(frame, pd.DataFrame):
        raise InputValidationError("observations must be a pandas DataFrame")
    if frame.empty:
        raise InputValidationError("observations frame is empty")

    try:
        validate_mart_columns(frame)
    except KeyError as exc:
        raise InputValidationError(str(exc)) from exc

    out = frame.copy()
    try:
        out["observed_hour"] = pd.to_datetime(out["observed_hour"], utc=True)
    except (TypeError, ValueError, pd.errors.OutOfBoundsDatetime) as exc:
        raise InputValidationError(
            f"observed_hour could not be parsed as timestamps: {exc}"
        ) from exc

    if out["station_id"].isna().any():
        raise InputValidationError("station_id contains nulls")

    dupes = out.duplicated(subset=["station_id", "observed_hour"], keep=False)
    if dupes.any():
        raise InputValidationError(
            f"duplicate (station_id, observed_hour) rows ({int(dupes.sum())}); "
            "inference requires unique hourly grain"
        )

    # Soft check: required numeric series should be mostly finite
    for col in REQUIRED_INPUT_COLUMNS:
        if col in {"station_id", "observed_hour"}:
            continue
        if col not in out.columns:
            continue
        if not pd.api.types.is_numeric_dtype(out[col]):
            coerced = pd.to_numeric(out[col], errors="coerce")
            if coerced.notna().sum() == 0:
                raise InputValidationError(f"column {col!r} has no numeric values after coercion")
            out[col] = coerced

    return out.sort_values(["station_id", "observed_hour"], kind="mergesort").reset_index(drop=True)
