"""Dagster orchestration package for Lahore AQI (ingest → dbt; no ML)."""

# Avoid importing definitions at package import time (keeps unit tests of
# failures/stages lightweight and sidesteps decorator side effects).
__all__ = ["defs"]


def __getattr__(name: str):
    if name == "defs":
        from lahore_aqi_dagster.definitions import defs as _defs

        return _defs
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
