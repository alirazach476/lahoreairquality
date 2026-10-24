"""API data access."""

from lahore_aqi_api.db.repository import AirQualityRepository, PostgresAirQualityRepository

__all__ = ["AirQualityRepository", "PostgresAirQualityRepository"]
