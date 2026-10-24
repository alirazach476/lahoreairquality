# Testing guide

## Default test suite (no real API calls)

The default suite uses **mocked HTTP** for OpenAQ and Open-Meteo. It does **not**
require API credentials or network access to external providers.

```bash
pip install -e ".[dev]" -e "ingestion/poller" -e "ingestion/consumer" -e "apps/api"
pytest
# or: make test
```

### Failure simulations and recovery

Controlled scenarios (OpenAQ/Open-Meteo/Redpanda/Postgres/MinIO down, malformed,
duplicate, stale, missing, delayed) live under `tests/resilience/`:

```bash
pytest tests/resilience -v
# or: make test-resilience
```

Expected behavior (portfolio write-up): [`failure-recovery.md`](failure-recovery.md).
HTTP catalog while the API is running: `GET /resilience/scenarios`.

Live external-API tests are collected but **automatically skipped** unless
`RUN_EXTERNAL_API_TESTS=1` is set. They never call the network in the default run.

### External client scenario coverage (mocked)

`tests/ingestion/test_external_clients_scenarios.py` covers:

| # | Scenario |
|---|----------|
| 1 | Successful OpenAQ response |
| 2 | Empty OpenAQ response |
| 3 | Invalid OpenAQ response |
| 4 | HTTP failure |
| 5 | Rate-limit response |
| 6 | Successful Open-Meteo response |
| 7 | Missing weather values |
| 8 | Invalid weather response |
| 9 | Timeout |
| 10 | Retry behavior |

Additional unit tests live under `tests/ingestion/test_openaq_client.py` and
`tests/ingestion/test_openmeteo_client.py`.

## Optional live external API integration tests

These hit the real OpenAQ and Open-Meteo APIs. They are **opt-in**.

### Enablement (both required)

1. Set environment variable: `RUN_EXTERNAL_API_TESTS=1`
2. Select the marker: `pytest -m integration`

### Credentials

| Client | Requirement |
|--------|-------------|
| Open-Meteo | No API key (public endpoints) |
| OpenAQ | `OPENAQ_API_KEY` in `.env` (see `.env.example`) |

Optional overrides: `OPENAQ_BASE_URL`, `OPENMETEO_BASE_URL`,
`OPENMETEO_ARCHIVE_BASE_URL`, `LAHORE_LATITUDE`, `LAHORE_LONGITUDE`.

### Commands

**PowerShell:**

```powershell
$env:RUN_EXTERNAL_API_TESTS = "1"
pytest -m integration -v
# or: make test-integration
```

**bash:**

```bash
RUN_EXTERNAL_API_TESTS=1 pytest -m integration -v
```

Run only one provider:

```bash
RUN_EXTERNAL_API_TESTS=1 pytest -m integration tests/integration/test_openmeteo_live.py -v
RUN_EXTERNAL_API_TESTS=1 pytest -m integration tests/integration/test_openaq_live.py -v
```

### Notes

- Live tests may skip if OpenAQ returns no Lahore locations at request time.
- Respect OpenAQ rate limits; avoid running live suites in tight CI loops without need.
- Never commit real API keys.

## End-to-end ingestion smoke test

Verifies the local pipeline with **deterministic mocked** OpenAQ / Open-Meteo
HTTP responses (no live external APIs):

```text
mocked clients → poller → Redpanda → consumer → PostgreSQL + MinIO
```

Checks: AQ + weather events created and published, consumer processing, normalized
Postgres rows, raw JSON in object storage, duplicate suppression, invalid-event
rejection, and useful structured logs.

### Command

```bash
make smoke
# or:
python scripts/run_smoke_test.py
```

The runner starts Compose infrastructure when Docker is available, stops the
long-running Compose poller/consumer to avoid races, then runs `pytest -m smoke`.

Requires: Docker (or an already-running Postgres + MinIO + Redpanda reachable via
`.env`), plus `pip install -e ".[dev]" -e ingestion/poller -e ingestion/consumer`.

## Data-quality unit tests

`tests/quality/` covers each rule in `lahore_air_quality.quality` (missing /
future timestamps, negatives, abnormal values, duplicates, units/pollutants,
missing weather, gaps, inactivity, staleness, and the report shape). See
[`data-quality.md`](data-quality.md).

```bash
pytest tests/quality -q
```

dbt mirrors the same rules under `models/quality/` (`dbt test --select path:models/quality`).

Production monitor (`python -m lahore_air_quality.quality`) reads PostgreSQL only.
Tests in `tests/quality/test_monitor_uses_database.py` assert it never loads synthetic fixtures.

Bootstrap history unit tests (mocked APIs): `tests/ingestion/test_bootstrap_history.py`.

## ML feature engineering tests

`tests/ml/features/` covers lag correctness, rolling windows, no future leakage,
and missing-data behavior. See [`ml-features.md`](ml-features.md).

```bash
pip install -e "./ml[dev]"
pytest tests/ml/features -q
```

## Database integration tests

Postgres-backed tests are marked `postgres` and skip automatically when Postgres
is unreachable. They are independent of the external API integration marker.
