# tests/

Automated tests organized by domain.

| Path | Focus |
|------|--------|
| `ingestion/` | Mocked OpenAQ / Open-Meteo client unit + scenario tests |
| `aqi/` | US EPA AQI calculator (breakpoints, missing/out-of-range) |
| `orchestration/` | Dagster stage/failure unit tests (no daemon required) |
| `smoke/` | End-to-end local ingestion pipeline (mocked APIs + Compose stack) |
| `integration/` | Optional **live** external API tests (opt-in; see `docs/testing.md`) |
| `transformations/` | AQI math, dbt-adjacent pure Python helpers |
| `ml/` | Features, metrics, forecast utilities |
| `api/` | FastAPI route and schema tests |

## Quick commands

```bash
# Default: mocked only, no API credentials required
pytest

# End-to-end ingestion smoke (starts Compose infra when Docker is available)
make smoke
# or: python scripts/run_smoke_test.py

# Optional live external APIs
RUN_EXTERNAL_API_TESTS=1 pytest -m integration
```

Full details: [`docs/testing.md`](../docs/testing.md).
