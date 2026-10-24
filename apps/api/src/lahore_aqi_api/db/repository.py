"""Data access for API routes (marts / raw / forecast artifacts).

Never returns or logs database credentials.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lahore_aqi_api.core.config import ApiSettings
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

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _CurrentRow:
    timestamp: datetime
    aqi: float
    aqi_category: str | None
    dominant_pollutant: str | None
    pollutants: PollutantReadings
    weather: WeatherReadings
    station_id: str | None
    scope: str


class AirQualityRepository(Protocol):
    def get_current(self, *, station_id: str | None = None) -> CurrentAirQualityResponse | None: ...

    def get_history(
        self,
        *,
        hours: int,
        station_id: str | None = None,
    ) -> AirQualityHistoryResponse: ...

    def get_forecasts(
        self, *, station_id: str | None = None, limit: int = 24
    ) -> ForecastResponse: ...

    def list_sensors(self) -> SensorsResponse: ...

    def get_data_quality(self) -> DataQualityResponse: ...


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _freshness(observed_at: datetime, *, threshold: int, now: datetime) -> DataFreshness:
    obs = _as_utc(observed_at)
    age = max(0.0, (now - obs).total_seconds())
    return DataFreshness(
        observed_at=obs,
        age_seconds=age,
        is_fresh=age <= threshold,
        freshness_threshold_seconds=threshold,
    )


def _relation_exists(session: Session, schema: str, table: str) -> bool:
    row = session.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema AND table_name = :table
            LIMIT 1
            """
        ),
        {"schema": schema, "table": table},
    ).first()
    return row is not None


class PostgresAirQualityRepository:
    """Read models from warehouse marts with raw-table fallbacks."""

    def __init__(self, session: Session, *, settings: ApiSettings) -> None:
        self._session = session
        self._settings = settings

    def get_current(self, *, station_id: str | None = None) -> CurrentAirQualityResponse | None:
        now = datetime.now(tz=UTC)
        row = (
            self._current_from_features(station_id)
            if station_id
            else self._current_from_city_mart()
        )
        if row is None and station_id is None:
            row = self._current_from_features(None)
        if row is None:
            return None
        return CurrentAirQualityResponse(
            timestamp=row.timestamp,
            aqi=row.aqi,
            aqi_category=row.aqi_category,
            dominant_pollutant=row.dominant_pollutant,
            pollutants=row.pollutants,
            weather=row.weather,
            station_id=row.station_id,
            scope=row.scope,
            freshness=_freshness(
                row.timestamp,
                threshold=self._settings.data_freshness_max_seconds,
                now=now,
            ),
        )

    def _current_from_city_mart(self) -> _CurrentRow | None:
        if not _relation_exists(self._session, "marts", "mart_lahore_aqi"):
            return None
        sql = text(
            """
            SELECT
                observed_hour,
                aqi,
                aqi_category,
                dominant_pollutant
            FROM marts.mart_lahore_aqi
            ORDER BY observed_hour DESC
            LIMIT 1
            """
        )
        try:
            result = self._session.execute(sql).mappings().first()
        except SQLAlchemyError as exc:
            logger.warning("city_mart_query_failed error=%s", type(exc).__name__)
            return None
        if result is None:
            return None
        # Enrich pollutants + weather from features city hour if available
        pollutants = PollutantReadings()
        weather = WeatherReadings()
        enriched = self._context_at_hour(_as_utc(result["observed_hour"]))
        if enriched is not None:
            pollutants, weather = enriched
        return _CurrentRow(
            timestamp=_as_utc(result["observed_hour"]),
            aqi=float(result["aqi"]),
            aqi_category=result.get("aqi_category"),
            dominant_pollutant=result.get("dominant_pollutant"),
            pollutants=pollutants,
            weather=weather,
            station_id=None,
            scope="city",
        )

    def _current_from_features(self, station_id: str | None) -> _CurrentRow | None:
        if not _relation_exists(self._session, "marts", "mart_air_quality_features"):
            return None
        params: dict[str, Any] = {}
        where = ""
        if station_id:
            where = "WHERE station_id = :station_id"
            params["station_id"] = station_id
        sql = text(
            f"""
            SELECT
                station_id,
                observed_hour,
                station_aqi,
                station_aqi_category,
                station_dominant_pollutant,
                city_aqi,
                city_aqi_category,
                city_dominant_pollutant,
                pm25, pm10, o3, no2, so2, co,
                temperature_c, relative_humidity_pct,
                wind_speed_ms, wind_direction_deg
            FROM marts.mart_air_quality_features
            {where}
            ORDER BY observed_hour DESC
            LIMIT 1
            """
        )
        try:
            result = self._session.execute(sql, params).mappings().first()
        except SQLAlchemyError as exc:
            logger.warning("features_query_failed error=%s", type(exc).__name__)
            return None
        if result is None:
            return None
        weather = WeatherReadings(
            temperature_c=_float_or_none(result.get("temperature_c")),
            relative_humidity_pct=_float_or_none(result.get("relative_humidity_pct")),
            wind_speed_ms=_float_or_none(result.get("wind_speed_ms")),
            wind_direction_deg=_float_or_none(result.get("wind_direction_deg")),
        )
        pollutants = PollutantReadings(
            pm25=_float_or_none(result.get("pm25")),
            pm10=_float_or_none(result.get("pm10")),
            o3=_float_or_none(result.get("o3")),
            no2=_float_or_none(result.get("no2")),
            so2=_float_or_none(result.get("so2")),
            co=_float_or_none(result.get("co")),
        )
        if station_id:
            aqi = result["station_aqi"]
            if aqi is None:
                return None
            return _CurrentRow(
                timestamp=_as_utc(result["observed_hour"]),
                aqi=float(aqi),
                aqi_category=result.get("station_aqi_category"),
                dominant_pollutant=result.get("station_dominant_pollutant"),
                pollutants=pollutants,
                weather=weather,
                station_id=str(result["station_id"]),
                scope="station",
            )
        # City-ish: use city_aqi from latest feature row
        aqi = result.get("city_aqi") or result.get("station_aqi")
        if aqi is None:
            return None
        return _CurrentRow(
            timestamp=_as_utc(result["observed_hour"]),
            aqi=float(aqi),
            aqi_category=result.get("city_aqi_category") or result.get("station_aqi_category"),
            dominant_pollutant=result.get("city_dominant_pollutant")
            or result.get("station_dominant_pollutant"),
            pollutants=pollutants,
            weather=weather,
            station_id=None,
            scope="city",
        )

    def _context_at_hour(self, hour: datetime) -> tuple[PollutantReadings, WeatherReadings] | None:
        if not _relation_exists(self._session, "marts", "mart_air_quality_features"):
            return None
        sql = text(
            """
            SELECT
                avg(pm25) AS pm25, avg(pm10) AS pm10, avg(o3) AS o3,
                avg(no2) AS no2, avg(so2) AS so2, avg(co) AS co,
                avg(temperature_c) AS temperature_c,
                avg(relative_humidity_pct) AS relative_humidity_pct,
                avg(wind_speed_ms) AS wind_speed_ms,
                avg(wind_direction_deg) AS wind_direction_deg
            FROM marts.mart_air_quality_features
            WHERE observed_hour = :hour
            """
        )
        try:
            result = self._session.execute(sql, {"hour": hour}).mappings().first()
        except SQLAlchemyError:
            return None
        if result is None:
            return None
        return (
            PollutantReadings(
                pm25=_float_or_none(result.get("pm25")),
                pm10=_float_or_none(result.get("pm10")),
                o3=_float_or_none(result.get("o3")),
                no2=_float_or_none(result.get("no2")),
                so2=_float_or_none(result.get("so2")),
                co=_float_or_none(result.get("co")),
            ),
            WeatherReadings(
                temperature_c=_float_or_none(result.get("temperature_c")),
                relative_humidity_pct=_float_or_none(result.get("relative_humidity_pct")),
                wind_speed_ms=_float_or_none(result.get("wind_speed_ms")),
                wind_direction_deg=_float_or_none(result.get("wind_direction_deg")),
            ),
        )

    def get_history(
        self,
        *,
        hours: int,
        station_id: str | None = None,
    ) -> AirQualityHistoryResponse:
        now = datetime.now(tz=UTC)
        start = now - timedelta(hours=hours)
        points: list[HistoryPoint] = []

        if station_id and _relation_exists(self._session, "marts", "mart_air_quality_features"):
            sql = text(
                """
                SELECT
                    station_id, observed_hour, station_aqi,
                    station_dominant_pollutant,
                    pm25, pm10, o3, no2, so2, co
                FROM marts.mart_air_quality_features
                WHERE station_id = :station_id
                  AND observed_hour >= :start
                ORDER BY observed_hour ASC
                """
            )
            rows = self._session.execute(sql, {"station_id": station_id, "start": start}).mappings()
            for r in rows:
                points.append(
                    HistoryPoint(
                        timestamp=_as_utc(r["observed_hour"]),
                        aqi=_float_or_none(r.get("station_aqi")),
                        dominant_pollutant=r.get("station_dominant_pollutant"),
                        pollutants=PollutantReadings(
                            pm25=_float_or_none(r.get("pm25")),
                            pm10=_float_or_none(r.get("pm10")),
                            o3=_float_or_none(r.get("o3")),
                            no2=_float_or_none(r.get("no2")),
                            so2=_float_or_none(r.get("so2")),
                            co=_float_or_none(r.get("co")),
                        ),
                        station_id=str(r["station_id"]),
                    )
                )
        elif _relation_exists(self._session, "marts", "mart_lahore_aqi"):
            sql = text(
                """
                SELECT observed_hour, aqi, dominant_pollutant
                FROM marts.mart_lahore_aqi
                WHERE observed_hour >= :start
                ORDER BY observed_hour ASC
                """
            )
            rows = self._session.execute(sql, {"start": start}).mappings()
            for r in rows:
                points.append(
                    HistoryPoint(
                        timestamp=_as_utc(r["observed_hour"]),
                        aqi=_float_or_none(r.get("aqi")),
                        dominant_pollutant=r.get("dominant_pollutant"),
                        pollutants=PollutantReadings(),
                        station_id=None,
                    )
                )

        return AirQualityHistoryResponse(
            start=start,
            end=now,
            station_id=station_id,
            points=points,
            count=len(points),
        )

    def get_forecasts(self, *, station_id: str | None = None, limit: int = 24) -> ForecastResponse:
        now = datetime.now(tz=UTC)
        # Prefer persisted forecast table when present
        if _relation_exists(self._session, "ml", "forecasts"):
            params: dict[str, Any] = {"limit": limit}
            where = "WHERE forecast_hour >= NOW() - INTERVAL '1 hour'"
            if station_id:
                where += " AND station_id = :station_id"
                params["station_id"] = station_id
            sql = text(
                f"""
                SELECT
                    forecast_hour,
                    predicted_aqi,
                    model_name,
                    model_version,
                    horizon_hours,
                    station_id,
                    origin_hour
                FROM ml.forecasts
                {where}
                ORDER BY forecast_hour ASC
                LIMIT :limit
                """
            )
            try:
                rows = list(self._session.execute(sql, params).mappings())
            except SQLAlchemyError as exc:
                logger.warning("forecast_table_query_failed error=%s", type(exc).__name__)
                rows = []
            if rows:
                forecasts = [
                    ForecastPoint(
                        forecast_timestamp=_as_utc(r["forecast_hour"]),
                        predicted_aqi=float(r["predicted_aqi"]),
                        model_name=str(r["model_name"]),
                        model_version=str(r["model_version"]),
                        forecast_horizon=int(r["horizon_hours"]),
                        station_id=r.get("station_id"),
                        origin_timestamp=(
                            _as_utc(r["origin_hour"]) if r.get("origin_hour") else None
                        ),
                    )
                    for r in rows
                ]
                return ForecastResponse(generated_at=now, forecasts=forecasts, count=len(forecasts))

        # Fallback: artifact metadata + optional predictions parquet
        return self._forecasts_from_artifacts(station_id=station_id, limit=limit, now=now)

    def _forecasts_from_artifacts(
        self,
        *,
        station_id: str | None,
        limit: int,
        now: datetime,
    ) -> ForecastResponse:
        root = Path(self._settings.forecast_artifact_dir)
        meta_files = sorted(root.glob("*_metadata.json")) if root.exists() else []
        if not meta_files:
            return ForecastResponse(generated_at=now, forecasts=[], count=0)

        meta_path = max(meta_files, key=lambda p: p.stat().st_mtime)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        model_name = str(meta.get("model") or "xgboost")
        created = str(meta.get("created_at_utc") or "unknown")
        stamp = created.replace(":", "").replace("-", "")[:15]
        model_version = f"{model_name}@{stamp}"
        horizon = int(meta.get("horizon") or 1)

        stem = meta_path.name.replace("_metadata.json", "")
        pred_path = meta_path.parent / f"{stem}_predictions.parquet"
        forecasts: list[ForecastPoint] = []
        if pred_path.exists():
            try:
                import pandas as pd

                frame = pd.read_parquet(pred_path)
                if station_id and "station_id" in frame.columns:
                    frame = frame.loc[frame["station_id"].astype(str) == station_id]
                # Prefer future-looking rows if forecast_hour-like columns exist
                y_col = next(
                    (
                        c
                        for c in (
                            "y_pred_xgboost",
                            "y_pred",
                            "predicted_aqi",
                        )
                        if c in frame.columns
                    ),
                    None,
                )
                time_col = next(
                    (
                        c
                        for c in ("observed_hour", "forecast_hour", "origin_hour")
                        if c in frame.columns
                    ),
                    None,
                )
                if y_col and time_col:
                    frame = frame.tail(limit)
                    for _, row in frame.iterrows():
                        origin = _as_utc(pd.Timestamp(row[time_col]).to_pydatetime())
                        forecasts.append(
                            ForecastPoint(
                                forecast_timestamp=origin + timedelta(hours=horizon),
                                predicted_aqi=float(row[y_col]),
                                model_name=model_name,
                                model_version=model_version,
                                forecast_horizon=horizon,
                                station_id=(
                                    str(row["station_id"])
                                    if "station_id" in frame.columns
                                    else station_id
                                ),
                                origin_timestamp=origin,
                            )
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning("forecast_artifact_read_failed error=%s", type(exc).__name__)

        if not forecasts:
            # Metadata-only stub point (transparent: predicted from last known N/A)
            forecasts = []

        return ForecastResponse(generated_at=now, forecasts=forecasts, count=len(forecasts))

    def list_sensors(self) -> SensorsResponse:
        sensors: list[SensorInfo] = []
        if _relation_exists(self._session, "marts", "mart_air_quality_features"):
            sql = text(
                """
                SELECT
                    station_id,
                    max(location_name) AS location_name,
                    avg(latitude) AS latitude,
                    avg(longitude) AS longitude,
                    max(source_name) AS source_name,
                    max(observed_hour) AS last_observed_at,
                    count(*) AS observation_count
                FROM marts.mart_air_quality_features
                GROUP BY station_id
                ORDER BY station_id
                """
            )
            try:
                for r in self._session.execute(sql).mappings():
                    sensors.append(
                        SensorInfo(
                            station_id=str(r["station_id"]),
                            location_name=r.get("location_name"),
                            latitude=_float_or_none(r.get("latitude")),
                            longitude=_float_or_none(r.get("longitude")),
                            source_name=r.get("source_name"),
                            last_observed_at=(
                                _as_utc(r["last_observed_at"])
                                if r.get("last_observed_at")
                                else None
                            ),
                            observation_count=int(r["observation_count"])
                            if r.get("observation_count") is not None
                            else None,
                        )
                    )
            except SQLAlchemyError as exc:
                logger.warning("sensors_features_failed error=%s", type(exc).__name__)

        if not sensors and _relation_exists(self._session, "raw", "air_quality_observations"):
            sql = text(
                """
                SELECT
                    station_id,
                    max(location_name) AS location_name,
                    avg(latitude) AS latitude,
                    avg(longitude) AS longitude,
                    max(source) AS source_name,
                    max(observed_at) AS last_observed_at,
                    count(*) AS observation_count
                FROM raw.air_quality_observations
                GROUP BY station_id
                ORDER BY station_id
                """
            )
            try:
                for r in self._session.execute(sql).mappings():
                    sensors.append(
                        SensorInfo(
                            station_id=str(r["station_id"]),
                            location_name=r.get("location_name"),
                            latitude=_float_or_none(r.get("latitude")),
                            longitude=_float_or_none(r.get("longitude")),
                            source_name=r.get("source_name"),
                            last_observed_at=(
                                _as_utc(r["last_observed_at"])
                                if r.get("last_observed_at")
                                else None
                            ),
                            observation_count=int(r["observation_count"])
                            if r.get("observation_count") is not None
                            else None,
                        )
                    )
            except SQLAlchemyError as exc:
                logger.warning("sensors_raw_failed error=%s", type(exc).__name__)

        return SensorsResponse(sensors=sensors, count=len(sensors))

    def get_data_quality(self) -> DataQualityResponse:
        now = datetime.now(tz=UTC)
        try:
            from lahore_air_quality.db.health import check_database_health
            from lahore_air_quality.quality.monitor import run_data_quality_monitor

            db_health = check_database_health(self._session.get_bind())
            result = run_data_quality_monitor(self._session)
            report = result.air_quality_report
            counts = QualityClassCounts()
            inactive: list[str] = []
            notes: list[str] = list(result.notes)
            aq_n = 0
            wx_n = 0
            if report is not None:
                data = report.as_dict()
                record_counts = data.get("record_counts") or {}
                counts = QualityClassCounts(
                    valid=int(record_counts.get("valid", 0)),
                    suspect=int(record_counts.get("suspect", 0)),
                    invalid=int(record_counts.get("invalid", 0)),
                )
                aq_n = int(record_counts.get("total") or 0)
                activity = data.get("sensor_activity") or {}
                inactive = [str(s) for s in (activity.get("inactive_stations") or [])]
                notes = list(data.get("notes") or notes)
            aq_n = aq_n or int(result.table_counts.get("raw.air_quality_observations") or 0)
            wx_n = int(result.table_counts.get("raw.weather_observations") or 0)
            if result.message:
                notes = [result.message, *notes]
            return DataQualityResponse(
                evaluated_at=now,
                database_healthy=db_health.healthy,
                air_quality_rows_evaluated=aq_n,
                weather_rows_evaluated=wx_n,
                class_counts=counts,
                inactive_stations=inactive,
                notes=notes,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("data_quality_failed error=%s", type(exc).__name__)
            return DataQualityResponse(
                evaluated_at=now,
                database_healthy=False,
                air_quality_rows_evaluated=0,
                weather_rows_evaluated=0,
                class_counts=QualityClassCounts(),
                notes=[f"Quality evaluation unavailable: {type(exc).__name__}"],
            )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
