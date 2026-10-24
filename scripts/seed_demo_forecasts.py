"""Seed ml.forecasts for local dashboard demo (shifts predictions onto upcoming hours)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT / "ml" / "training" / "artifacts" / "xgboost" / "xgboost_predictions.parquet"


def main() -> int:
    if not PRED.exists():
        raise SystemExit(f"missing predictions: {PRED}")

    df = pd.read_parquet(PRED).tail(24).reset_index(drop=True)
    now = datetime.now(tz=UTC).replace(minute=0, second=0, microsecond=0)
    engine = create_engine("postgresql+psycopg://lahore:change_me@localhost:5432/lahore_aqi")

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS ml"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ml.forecasts (
                    forecast_hour timestamptz NOT NULL,
                    predicted_aqi double precision NOT NULL,
                    model_name text NOT NULL,
                    model_version text NOT NULL,
                    horizon_hours integer NOT NULL,
                    station_id text NULL,
                    origin_hour timestamptz NULL,
                    PRIMARY KEY (forecast_hour, model_name, model_version)
                )
                """
            )
        )
        conn.execute(text("DELETE FROM ml.forecasts WHERE model_name = 'xgboost'"))
        for i, row in df.iterrows():
            origin = now + timedelta(hours=int(i))
            forecast_hour = origin + timedelta(hours=1)
            # Training target is PM2.5; map roughly to AQI-like scale for display.
            pm25 = float(row["y_pred_xgboost"])
            predicted_aqi = max(0.0, min(500.0, pm25 * 2.5))
            conn.execute(
                text(
                    """
                    INSERT INTO ml.forecasts (
                        forecast_hour, predicted_aqi, model_name, model_version,
                        horizon_hours, station_id, origin_hour
                    ) VALUES (
                        :forecast_hour, :predicted_aqi, :model_name, :model_version,
                        :horizon_hours, :station_id, :origin_hour
                    )
                    ON CONFLICT (forecast_hour, model_name, model_version) DO UPDATE
                    SET predicted_aqi = EXCLUDED.predicted_aqi,
                        horizon_hours = EXCLUDED.horizon_hours,
                        station_id = EXCLUDED.station_id,
                        origin_hour = EXCLUDED.origin_hour
                    """
                ),
                {
                    "forecast_hour": forecast_hour,
                    "predicted_aqi": predicted_aqi,
                    "model_name": "xgboost",
                    "model_version": "demo-synthetic",
                    "horizon_hours": 1,
                    "station_id": None,
                    "origin_hour": origin,
                },
            )
        n = conn.execute(text("SELECT COUNT(*) FROM ml.forecasts")).scalar_one()
    print(f"seeded ml.forecasts rows={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
