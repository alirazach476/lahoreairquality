"""Reusable OpenAQ mock payloads for unit/integration-layer tests."""

from __future__ import annotations

from typing import Any


def location_payload(location_id: int = 9001) -> dict[str, Any]:
    return {
        "id": location_id,
        "name": "US Consulate Lahore",
        "locality": "Lahore",
        "timezone": "Asia/Karachi",
        "country": {"id": 1, "code": "PK", "name": "Pakistan"},
        "provider": {"id": 10, "name": "AirNow"},
        "isMobile": False,
        "isMonitor": True,
        "sensors": [
            {
                "id": 501,
                "name": "PM2.5",
                "parameter": {
                    "id": 2,
                    "name": "pm25",
                    "units": "µg/m³",
                    "displayName": "PM2.5",
                },
            }
        ],
        "coordinates": {"latitude": 31.5601, "longitude": 74.3359},
    }


def locations_success_response() -> dict[str, Any]:
    return {
        "meta": {"found": 1, "page": 1, "limit": 100},
        "results": [location_payload()],
    }


def locations_empty_response() -> dict[str, Any]:
    return {"meta": {"found": 0, "page": 1, "limit": 100}, "results": []}


def latest_success_response() -> dict[str, Any]:
    return {
        "meta": {"found": 1, "page": 1, "limit": 100},
        "results": [
            {
                "datetime": {
                    "utc": "2026-10-24T05:00:00Z",
                    "local": "2026-10-24T10:00:00+05:00",
                },
                "value": 87.5,
                "coordinates": {"latitude": 31.5601, "longitude": 74.3359},
                "sensorsId": 501,
                "locationsId": 9001,
            }
        ],
    }


def latest_empty_response() -> dict[str, Any]:
    return {"meta": {"found": 0, "page": 1, "limit": 100}, "results": []}
