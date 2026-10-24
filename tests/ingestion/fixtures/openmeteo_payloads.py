"""Reusable Open-Meteo mock payloads for unit/integration-layer tests."""

from __future__ import annotations

from typing import Any


def forecast_success_response() -> dict[str, Any]:
    return {
        "latitude": 31.5,
        "longitude": 74.375,
        "generationtime_ms": 0.12,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "elevation": 217.0,
        "current_units": {
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "precipitation": "mm",
            "wind_speed_10m": "m/s",
            "wind_direction_10m": "°",
            "surface_pressure": "hPa",
        },
        "current": {
            "time": "2026-10-24T05:00",
            "temperature_2m": 28.5,
            "relative_humidity_2m": 55,
            "precipitation": 0.0,
            "wind_speed_10m": 3.2,
            "wind_direction_10m": 180,
            "surface_pressure": 1008.2,
        },
        "hourly_units": {
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "precipitation": "mm",
            "wind_speed_10m": "m/s",
            "wind_direction_10m": "°",
            "surface_pressure": "hPa",
        },
        "hourly": {
            "time": ["2026-10-24T00:00", "2026-10-24T01:00"],
            "temperature_2m": [28.5, 29.0],
            "relative_humidity_2m": [50, 52],
            "precipitation": [0.0, 0.1],
            "wind_speed_10m": [2.5, 2.8],
            "wind_direction_10m": [90, 100],
            "surface_pressure": [1008.0, 1007.5],
        },
    }


def forecast_with_missing_values() -> dict[str, Any]:
    payload = forecast_success_response()
    payload.pop("current", None)
    payload["hourly"] = {
        "time": ["2026-10-24T00:00", "2026-10-24T01:00"],
        "temperature_2m": [27.0, None],
        "relative_humidity_2m": [60, 61],
        "precipitation": [None, 0.2],
        "wind_speed_10m": [1.5, 1.6],
        "wind_direction_10m": [45, 50],
        "surface_pressure": [1005.0, 1004.5],
    }
    return payload


def invalid_forecast_response() -> dict[str, Any]:
    """Hourly arrays with mismatched lengths — fails validation."""
    payload = forecast_success_response()
    payload.pop("current", None)
    payload["hourly"]["temperature_2m"] = [1.0]
    return payload
