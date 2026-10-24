# apps/api

FastAPI backend for the Lahore Air Quality Intelligence Platform.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service + DB health |
| GET | `/api/air-quality/current` | Latest AQI (+ pollutants, freshness) |
| GET | `/api/air-quality/history` | Recent history (`hours`, optional `station_id`) |
| GET | `/api/forecast` | Model forecasts |
| GET | `/api/sensors` | Station / sensor list |
| GET | `/api/data-quality` | Quality monitoring summary |

Interactive docs: `/docs` (OpenAPI), `/redoc`.

## Run locally

```bash
pip install -e "./apps/api[dev]"
# Platform DB settings via env / .env (POSTGRES_*). Never commit secrets.
# CORS for local React (override with API_CORS_ORIGINS):
#   http://localhost:5173,http://localhost:3000

lahore-aqi-api
# or:
uvicorn lahore_aqi_api.main:app --host 0.0.0.0 --port 8000 --reload
```

Database credentials are read from environment-based platform settings and are
**never** included in API responses or health payloads.

## Configuration (env)

| Variable | Role |
|----------|------|
| `POSTGRES_*` | DB connection (via `lahore_air_quality.config`) |
| `API_HOST` / `API_PORT` | Bind address |
| `API_CORS_ORIGINS` | Comma-separated allowed origins |
| `DATA_FRESHNESS_MAX_SECONDS` | Freshness threshold (default 7200) |
| `FORECAST_ARTIFACT_DIR` | Fallback forecast artifacts path |

## Tests

```bash
pytest tests/api -q
```

Tests use an in-memory fake repository (no live Postgres required).
