"""Discover Lahore OpenAQ locations/sensors and verify pollutant availability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ingestion.bootstrap_history.settings import TARGET_POLLUTANTS
from lahore_aqi_poller.clients.openaq.client import OpenAQClient
from lahore_aqi_poller.clients.openaq.models import OpenAQLocation, SensorBase


def _canonical_pollutant(name: str) -> str:
    cleaned = name.strip().lower().replace(" ", "")
    aliases = {"pm2.5": "pm25", "pm25": "pm25", "pm10": "pm10"}
    return aliases.get(cleaned, cleaned)


def _parse_openaq_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class DiscoveredSensor:
    location_id: int
    location_name: str | None
    sensor_id: int
    pollutant: str
    unit: str
    location_first: datetime | None
    location_last: datetime | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "location_id": self.location_id,
            "location_name": self.location_name,
            "sensor_id": self.sensor_id,
            "pollutant": self.pollutant,
            "unit": self.unit,
            "location_datetime_first": (
                self.location_first.isoformat() if self.location_first else None
            ),
            "location_datetime_last": (
                self.location_last.isoformat() if self.location_last else None
            ),
        }


@dataclass
class DiscoveryReport:
    locations_found: int = 0
    sensors_total: int = 0
    target_sensors: list[DiscoveredSensor] = field(default_factory=list)
    pollutants_available: list[str] = field(default_factory=list)
    skipped_sensors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "locations_found": self.locations_found,
            "sensors_total": self.sensors_total,
            "target_sensors": [s.as_dict() for s in self.target_sensors],
            "pollutants_available": self.pollutants_available,
            "skipped_sensors": self.skipped_sensors,
            "notes": self.notes,
        }


def discover_pm_sensors(
    client: OpenAQClient,
    *,
    radius_m: int | None = None,
    target_pollutants: frozenset[str] = TARGET_POLLUTANTS,
) -> tuple[list[OpenAQLocation], DiscoveryReport]:
    """Call OpenAQ discovery; keep only sensors whose parameter is PM2.5/PM10."""
    kwargs: dict[str, Any] = {}
    if radius_m is not None:
        kwargs["radius_m"] = radius_m
    locations = client.discover_lahore_locations(**kwargs)
    report = DiscoveryReport(locations_found=len(locations))
    if not locations:
        report.notes.append(
            "No Lahore locations returned by OpenAQ discovery. "
            "Check OPENAQ_API_KEY, network, and radius."
        )
        return locations, report

    pollutants: set[str] = set()
    for loc in locations:
        first = _parse_openaq_dt(loc.datetime_first.utc if loc.datetime_first else None)
        last = _parse_openaq_dt(loc.datetime_last.utc if loc.datetime_last else None)
        for sensor in loc.sensors:
            report.sensors_total += 1
            code = _canonical_pollutant(sensor.parameter.name)
            pollutants.add(code)
            if code not in target_pollutants:
                report.skipped_sensors.append(
                    {
                        "location_id": loc.id,
                        "sensor_id": sensor.id,
                        "pollutant": code,
                        "reason": "not_in_target_pollutants",
                    }
                )
                continue
            report.target_sensors.append(
                DiscoveredSensor(
                    location_id=loc.id,
                    location_name=loc.name,
                    sensor_id=sensor.id,
                    pollutant=code,
                    unit=sensor.parameter.units,
                    location_first=first,
                    location_last=last,
                )
            )

    report.pollutants_available = sorted(pollutants)
    if not report.target_sensors:
        report.notes.append(
            "Locations were found but none expose pm25/pm10 sensors in the "
            f"API response. Available pollutants: {report.pollutants_available}"
        )
    else:
        report.notes.append(
            "Sensor IDs and date bounds come from the live OpenAQ response — none are hard-coded."
        )
    return locations, report


def location_by_id(locations: list[OpenAQLocation]) -> dict[int, OpenAQLocation]:
    return {loc.id: loc for loc in locations}


def sensor_on_location(location: OpenAQLocation, sensor_id: int) -> SensorBase | None:
    return location.sensor_by_id.get(sensor_id)
