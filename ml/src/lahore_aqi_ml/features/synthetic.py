"""Deterministic synthetic mart-shaped frames for **tests and local demos only**.

Never import this module from production monitoring, ingestion, or bootstrap.
Production feature builds must use ``--from-parquet`` / warehouse extracts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from lahore_aqi_ml.features.columns import AQ_SERIES_COLUMNS, WEATHER_COLUMNS


def make_synthetic_mart_frame(
    *,
    n_hours: int = 72,
    stations: tuple[str, ...] = ("PK-LHR-01", "PK-LHR-02"),
    start: datetime | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a unique hourly ``mart_air_quality_features``-shaped DataFrame."""
    rng = np.random.default_rng(seed)
    t0 = start or datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    rows: list[dict] = []

    for station_i, station in enumerate(stations):
        for h in range(n_hours):
            ts = t0 + timedelta(hours=h)
            # Smooth diurnal + station offset (no future peeking in generator itself)
            diurnal = 40 + 30 * np.sin(2 * np.pi * (h % 24) / 24) + 5 * station_i
            noise = float(rng.normal(0, 3))
            pm25 = max(5.0, diurnal + noise)
            station_aqi = min(500.0, max(0.0, pm25 * 2.1))
            city_aqi = station_aqi + float(rng.normal(0, 2))
            row = {
                "station_id": station,
                "observed_hour": ts,
                "location_name": "Lahore",
                "latitude": 31.52 + 0.01 * station_i,
                "longitude": 74.36,
                "source_name": "synthetic",
                "pm25": pm25,
                "pm10": pm25 * 1.4,
                "o3": 0.03 + 0.01 * np.sin(h / 12),
                "no2": 20 + h % 7,
                "so2": 5 + (h % 5),
                "co": 0.5,
                "station_aqi": station_aqi,
                "station_aqi_category": "Moderate",
                "station_dominant_pollutant": "pm25",
                "temperature_c": 20 + 8 * np.sin(2 * np.pi * h / 24),
                "relative_humidity_pct": 50 + 10 * np.cos(2 * np.pi * h / 24),
                "precipitation_mm": 0.0 if h % 17 else 1.5,
                "wind_speed_ms": 2 + (h % 5) * 0.3,
                "wind_direction_deg": float((h * 15) % 360),
                "pressure_hpa": 1010.0,
                "city_aqi": city_aqi,
                "city_aqi_category": "Moderate",
                "city_dominant_pollutant": "pm25",
                "pm25_rolling_24h_avg": np.nan,  # unused; ML recomputes rollings
                "observation_count": 1,
                "last_ingested_at_utc": ts,
            }
            rows.append(row)

    frame = pd.DataFrame(rows)
    # Ensure required numeric dtypes
    for col in AQ_SERIES_COLUMNS + WEATHER_COLUMNS:
        frame[col] = frame[col].astype("float64")
    return frame
