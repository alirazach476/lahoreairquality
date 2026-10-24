# Lahore AQI API

FastAPI service under `apps/api`.

## Run

```bash
pip install -e "./apps/api[dev]"
lahore-aqi-api
```

OpenAPI UI: http://localhost:8000/docs

## Endpoints

- `GET /health`
- `GET /api/air-quality/current`
- `GET /api/air-quality/history`
- `GET /api/forecast`
- `GET /api/sensors`
- `GET /api/data-quality`

CORS defaults allow local React (`localhost:5173`, `localhost:3000`).
Override with `API_CORS_ORIGINS`. Database credentials are never returned.
