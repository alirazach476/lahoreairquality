"""API test fixtures — fake repository, no live database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from lahore_air_quality.db.health import DatabaseHealth
from lahore_aqi_api.main import create_app
from lahore_aqi_api.schemas.air_quality import (
    AirQualityHistoryResponse,
    CurrentAirQualityResponse,
    HistoryPoint,
    PollutantReadings,
    WeatherReadings,
)
from lahore_aqi_api.schemas.common import DataFreshness
from lahore_aqi_api.schemas.forecast import ForecastPoint, ForecastResponse
from lahore_aqi_api.schemas.quality import DataQualityResponse, QualityClassCounts
from lahore_aqi_api.schemas.sensors import SensorInfo, SensorsResponse


class FakeRepository:
    """In-memory stand-in for PostgresAirQualityRepository."""

    def __init__(self) -> None:
        now = datetime.now(tz=UTC)
        self.now = now
        self.current = CurrentAirQualityResponse(
            timestamp=now - timedelta(minutes=20),
            aqi=142.0,
            aqi_category="Unhealthy for Sensitive Groups",
            dominant_pollutant="pm25",
            pollutants=PollutantReadings(pm25=55.0, pm10=80.0, o3=0.04, no2=22.0),
            weather=WeatherReadings(
                temperature_c=28.5,
                relative_humidity_pct=42.0,
                wind_speed_ms=2.4,
                wind_direction_deg=210.0,
            ),
            station_id=None,
            scope="city",
            freshness=DataFreshness(
                observed_at=now - timedelta(minutes=20),
                age_seconds=1200.0,
                is_fresh=True,
                freshness_threshold_seconds=7200,
            ),
        )
        self.history = AirQualityHistoryResponse(
            start=now - timedelta(hours=24),
            end=now,
            station_id=None,
            points=[
                HistoryPoint(
                    timestamp=now - timedelta(hours=h),
                    aqi=100.0 + h,
                    dominant_pollutant="pm25",
                    pollutants=PollutantReadings(pm25=40.0 + h),
                    station_id=None,
                )
                for h in range(3)
            ],
            count=3,
        )
        self.forecasts = ForecastResponse(
            generated_at=now,
            forecasts=[
                ForecastPoint(
                    forecast_timestamp=now + timedelta(hours=1),
                    predicted_aqi=150.0,
                    model_name="xgboost_h1",
                    model_version="xgboost_h1@20261024T094049",
                    forecast_horizon=1,
                    station_id="S1",
                    origin_timestamp=now,
                )
            ],
            count=1,
        )
        self.sensors = SensorsResponse(
            sensors=[
                SensorInfo(
                    station_id="S1",
                    location_name="Lahore Test",
                    latitude=31.52,
                    longitude=74.36,
                    source_name="openaq",
                    last_observed_at=now,
                    observation_count=10,
                )
            ],
            count=1,
        )
        self.quality = DataQualityResponse(
            evaluated_at=now,
            database_healthy=True,
            air_quality_rows_evaluated=100,
            weather_rows_evaluated=50,
            class_counts=QualityClassCounts(valid=90, suspect=8, invalid=2),
            inactive_stations=[],
            notes=["test fixture"],
        )
        self.return_empty_current = False
        self.return_empty_forecast = False

    def get_current(self, *, station_id: str | None = None) -> CurrentAirQualityResponse | None:
        if self.return_empty_current:
            return None
        if station_id:
            return self.current.model_copy(update={"station_id": station_id, "scope": "station"})
        return self.current

    def get_history(
        self, *, hours: int, station_id: str | None = None
    ) -> AirQualityHistoryResponse:
        return self.history.model_copy(update={"station_id": station_id})

    def get_forecasts(self, *, station_id: str | None = None, limit: int = 24) -> ForecastResponse:
        if self.return_empty_forecast:
            return ForecastResponse(generated_at=self.now, forecasts=[], count=0)
        return self.forecasts

    def list_sensors(self) -> SensorsResponse:
        return self.sensors

    def get_data_quality(self) -> DataQualityResponse:
        return self.quality


@pytest.fixture
def fake_repo() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def client(fake_repo: FakeRepository) -> TestClient:
    application = create_app(for_testing=True)
    application.state.repository = fake_repo
    application.state.health_checker = lambda: DatabaseHealth(
        healthy=True,
        message="PostgreSQL connection OK",
        server_version="16.0",
    )
    with TestClient(application) as test_client:
        yield test_client
