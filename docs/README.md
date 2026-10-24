# docs/

Project documentation for architecture, data sources, and operator runbooks.

| Doc | Purpose |
|-----|---------|
| `architecture.md` | System context and component responsibilities |
| `data-sources.md` | External APIs and how to supply credentials |
| `data-model.md` | Schemas, keys, indexes, and idempotency |
| `local-stack.md` | Full Docker Compose stack (up/down/logs, tests, dbt, training) |
| `ci.md` | GitHub Actions CI layout |
| `failure-recovery.md` | Failure simulations, retries, recovery (portfolio / interview) |
| `testing.md` | Default mocked suite + optional live API tests |
| `data-model.md` | Raw tables + dbt lineage |
| `aqi.md` | US EPA AQI methodology, units, averaging periods |
| `data-quality.md` | Quality rules, valid/suspect/invalid, observability report |
| `bootstrap-history.md` | Historical OpenAQ + Open-Meteo import into raw tables |
| `ml-features.md` | Time-aware ML features (lags, rolling, weather, calendar) |
| `ml-evaluation.md` | Chronological splits, baselines, MAE/RMSE/MAPE |
| `ml-sarima.md` | SARIMA training, naive comparison, artifacts |
| `api.md` | HTTP API reference (later) |
