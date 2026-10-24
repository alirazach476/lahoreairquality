"""Fixtures for ML feature tests."""

from __future__ import annotations

import pandas as pd
import pytest

from lahore_aqi_ml.features.synthetic import make_synthetic_mart_frame


@pytest.fixture
def mart_frame() -> pd.DataFrame:
    return make_synthetic_mart_frame(n_hours=48, stations=("S1", "S2"), seed=7)


@pytest.fixture
def tiny_series_frame() -> pd.DataFrame:
    """Minimal two-station hourly frame with known numeric values for exact checks."""
    rows = []
    for station, offset in (("A", 0), ("B", 100)):
        for h in range(10):
            rows.append(
                {
                    "station_id": station,
                    "observed_hour": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(hours=h),
                    "location_name": "Lahore",
                    "latitude": 31.5,
                    "longitude": 74.3,
                    "source_name": "test",
                    "pm25": float(offset + h),
                    "pm10": float(offset + h + 1),
                    "o3": 0.05,
                    "no2": 10.0,
                    "so2": 2.0,
                    "co": 0.4,
                    "station_aqi": float(offset + h * 2),
                    "station_aqi_category": "Good",
                    "station_dominant_pollutant": "pm25",
                    "temperature_c": 25.0,
                    "relative_humidity_pct": 40.0,
                    "precipitation_mm": 0.0,
                    "wind_speed_ms": 3.0,
                    "wind_direction_deg": 90.0,
                    "pressure_hpa": 1012.0,
                    "city_aqi": float(h * 2),
                    "city_aqi_category": "Good",
                    "city_dominant_pollutant": "pm25",
                    "pm25_rolling_24h_avg": None,
                    "observation_count": 1,
                    "last_ingested_at_utc": pd.Timestamp("2026-01-01", tz="UTC"),
                }
            )
    return pd.DataFrame(rows)
