# apps/

Runnable user-facing and service applications.

| App | Role |
|-----|------|
| `api/` | FastAPI backend that serves warehouse and forecast data |
| `dashboard/` | React dashboard for AQI, weather context, and forecasts |

```bash
# API
pip install -e "./apps/api[dev]" && lahore-aqi-api

# Dashboard
cd apps/dashboard && cp .env.example .env && npm install && npm run dev
```
