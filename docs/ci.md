# Continuous integration

GitHub Actions workflows live under `.github/workflows/`.

## Normal CI (`ci.yml`)

Runs on **push** and **pull_request**. No production secrets.

| Job | What it checks |
|-----|----------------|
| **Backend** | `ruff format --check`, `ruff check`, `pytest` (excludes `integration` + `smoke`). CI Postgres for `postgres`-marked tests. |
| **Frontend** | `npm ci`, `npm run lint` (`tsc --noEmit`), `npm run build` |
| **dbt parse** | `dbt deps` + `dbt parse` (no warehouse) |
| **dbt test** | Alembic migrate → `dbt seed` → `dbt run` → `dbt test` on CI Postgres |

Dependency caching: pip (`setup-python` cache) and npm (`setup-node` cache).

### What is excluded from normal CI

| Suite | Why | Where |
|-------|-----|--------|
| `@pytest.mark.integration` | Live OpenAQ / Open-Meteo | `integration-external.yml` |
| `@pytest.mark.smoke` | Docker Compose e2e | local `make smoke` |
| Deploy | Not implemented | — |

## External integration (`integration-external.yml`)

- Trigger: **workflow_dispatch** or weekly cron
- Sets `RUN_EXTERNAL_API_TESTS=1` and runs `pytest -m integration`
- Optional repo secret: `OPENAQ_API_KEY` (Open-Meteo needs none)

## Local equivalents

```bash
# Backend
ruff format --check .
ruff check .
pytest -m "not integration and not smoke"

# Frontend
cd apps/dashboard && npm ci && npm run lint && npm run build

# dbt parse
cd dbt/lahore_air_quality && dbt deps && dbt parse
```
