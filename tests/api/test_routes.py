"""FastAPI route tests against a fake repository (no live Postgres)."""

from __future__ import annotations

from lahore_air_quality.db.health import DatabaseHealth


def test_health_ok(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert "password" not in response.text.lower()
    assert "postgres://" not in response.text.lower()


def test_health_degraded(client, fake_repo) -> None:
    client.app.state.health_checker = lambda: DatabaseHealth(
        healthy=False,
        message="PostgreSQL connection failed: OperationalError",
    )
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert "password" not in response.text.lower()


def test_current_air_quality(client) -> None:
    response = client.get("/api/air-quality/current")
    assert response.status_code == 200
    body = response.json()
    assert body["aqi"] == 142.0
    assert body["dominant_pollutant"] == "pm25"
    assert "timestamp" in body
    assert "freshness" in body
    assert body["freshness"]["is_fresh"] is True
    assert "pm25" in body["pollutants"]


def test_current_air_quality_not_found(client, fake_repo) -> None:
    fake_repo.return_empty_current = True
    response = client.get("/api/air-quality/current")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_current_with_station_filter(client) -> None:
    response = client.get("/api/air-quality/current", params={"station_id": "S1"})
    assert response.status_code == 200
    assert response.json()["station_id"] == "S1"
    assert response.json()["scope"] == "station"


def test_history(client) -> None:
    response = client.get("/api/air-quality/history", params={"hours": 24})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert len(body["points"]) == 3


def test_history_hours_too_large(client) -> None:
    response = client.get("/api/air-quality/history", params={"hours": 10_000})
    assert response.status_code == 422


def test_forecast(client) -> None:
    response = client.get("/api/forecast")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    point = body["forecasts"][0]
    assert "forecast_timestamp" in point
    assert point["predicted_aqi"] == 150.0
    assert point["model_name"]
    assert point["model_version"]
    assert point["forecast_horizon"] == 1


def test_forecast_not_found(client, fake_repo) -> None:
    fake_repo.return_empty_forecast = True
    response = client.get("/api/forecast")
    assert response.status_code == 404


def test_sensors(client) -> None:
    response = client.get("/api/sensors")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["sensors"][0]["station_id"] == "S1"


def test_data_quality(client) -> None:
    response = client.get("/api/data-quality")
    assert response.status_code == 200
    body = response.json()
    assert body["database_healthy"] is True
    assert body["class_counts"]["valid"] == 90
    assert "password" not in response.text.lower()


def test_openapi_available(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/resilience/scenarios" in paths
    assert "/resilience/status" in paths
    assert "/api/air-quality/current" in paths
    assert "/api/air-quality/history" in paths
    assert "/api/forecast" in paths
    assert "/api/sensors" in paths
    assert "/api/data-quality" in paths


def test_resilience_scenarios_catalog(client) -> None:
    response = client.get("/resilience/scenarios")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 10
    ids = {s["id"] for s in body["scenarios"]}
    assert "openaq_unavailable" in ids
    assert "delayed_event" in ids
    detail = client.get("/resilience/scenarios/postgres_unavailable")
    assert detail.status_code == 200
    assert "offset" in detail.json()["retry"].lower() or "commit" in detail.json()["retry"].lower()


def test_resilience_status_ok(client) -> None:
    response = client.get("/resilience/status")
    assert response.status_code == 200
    body = response.json()
    assert body["overall_healthy"] is True
    assert body["scenario_catalog_size"] == 10
    assert body["components"][0]["name"] == "postgres"


def test_cors_preflight(client) -> None:
    response = client.options(
        "/api/air-quality/current",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
