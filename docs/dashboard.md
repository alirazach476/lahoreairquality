# Dashboard

React + Vite app in `apps/dashboard`.

```bash
cd apps/dashboard
cp .env.example .env   # set VITE_API_BASE_URL
npm install
npm run dev
```

Requires the FastAPI service (`apps/api`). Panels load live API data with
loading / error / empty states — no hard-coded production metrics.
