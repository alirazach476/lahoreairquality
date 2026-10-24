"""Ensure dbt AQI seed stays aligned with the Python EPA breakpoint table."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from lahore_air_quality.aqi.breakpoints import all_breakpoint_bands

SEED_PATH = (
    Path(__file__).resolve().parents[2]
    / "dbt"
    / "lahore_air_quality"
    / "seeds"
    / "aqi_breakpoints.csv"
)


def test_dbt_seed_matches_python_breakpoints() -> None:
    assert SEED_PATH.is_file(), f"missing seed: {SEED_PATH}"

    with SEED_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    python_bands = all_breakpoint_bands()
    assert len(rows) == len(python_bands)

    for row, band in zip(rows, python_bands, strict=True):
        assert row["pollutant"] == band.pollutant
        assert row["unit"] == band.unit
        assert Decimal(row["breakpoint_low"]) == band.concentration_low
        assert Decimal(row["breakpoint_high"]) == band.concentration_high
        assert int(row["aqi_low"]) == band.aqi_low
        assert int(row["aqi_high"]) == band.aqi_high
        assert row["category"] == band.category
