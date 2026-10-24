# apps/dashboard

React dashboard for the **Lahore Air Quality Intelligence Platform**.

Consumes the FastAPI service (`apps/api`) — no fabricated production values.
Loading, error, and empty states are handled per panel.

## Setup

```bash
cd apps/dashboard
cp .env.example .env
# edit VITE_API_BASE_URL if needed (default http://localhost:8000)
npm install
npm run dev
```

Open http://localhost:5173 — ensure the API is running (`lahore-aqi-api`).

## Environment

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | FastAPI base URL (required, no trailing slash) |

## Live API wiring

| Dashboard need | Endpoint |
|----------------|----------|
| Current AQI + weather | `GET /api/air-quality/current` |
| History chart | `GET /api/air-quality/history?hours=48` |
| Forecast chart | `GET /api/forecast?limit=48` |
| Sensors | `GET /api/sensors` |
| Data quality | `GET /api/data-quality` |

Handled client-side: loading, network failure, API errors, empty (incl. 404),
stale data (`freshness.is_fresh === false`). No secrets in the frontend — only
`VITE_API_BASE_URL`.

Timestamps are shown in **Lahore local time** (`Asia/Karachi`). The original API
ISO string is preserved in tooltips / “API timestamp” text.

## Stack

- React 19 + Vite + TypeScript  
- Custom CSS (no UI kit)  
- SVG charts (no chart library)  
- `src/api/client.ts` service layer  

## Build

```bash
npm run build
npm run preview
```
