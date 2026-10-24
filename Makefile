.PHONY: help install lint test test-resilience test-integration smoke \
	compose-up compose-down compose-logs compose-ps compose-build \
	compose-test compose-dbt compose-dbt-test compose-train compose-train-synthetic \
	db-upgrade db-downgrade db-current \
	dbt-deps dbt-seed dbt-run dbt-test dbt-freshness \
	dagster-dev clean

DBT_DIR := dbt/lahore_air_quality
DBT_PROFILES_DIR ?= $(CURDIR)/$(DBT_DIR)
DAGSTER_DIR := orchestration/dagster
COMPOSE ?= docker compose

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

install: ## Install workspace packages in editable mode (requires uv or pip)
	@echo "Prefer: uv sync"
	@echo "Or:     pip install -e \".[dev]\" && pip install -e apps/api -e ingestion/poller -e ingestion/consumer -e ml -e orchestration/dagster"

lint: ## Run ruff format check + linter
	ruff format --check .
	ruff check .

test: ## Run default suite on host (mocked; excludes live integration + smoke)
	pytest -m "not integration and not smoke"

test-resilience: ## Controlled failure simulations + recovery assertions
	pytest tests/resilience -v

poller-once: ## Run a single poller cycle (requires OPENAQ_API_KEY for AQ)
	python -m ingestion.poller --once

consumer: ## Run the Redpanda → S3/Postgres consumer
	python -m ingestion.consumer

test-integration: ## Run live external API tests (requires RUN_EXTERNAL_API_TESTS=1)
	@echo "Ensure RUN_EXTERNAL_API_TESTS=1 is set in your environment"
	pytest -m integration -v

smoke: ## End-to-end ingestion smoke test (mocked APIs; starts Compose infra)
	python scripts/run_smoke_test.py

# --- Docker Compose (full stack) ---

compose-build: ## Build all Compose images
	$(COMPOSE) build

compose-up: ## Start full stack (infra + poller/consumer + MLflow + Dagster + API + dashboard)
	$(COMPOSE) up -d --build

compose-down: ## Stop stack (keeps volumes)
	$(COMPOSE) down

compose-logs: ## Tail logs for application services
	$(COMPOSE) logs -f poller consumer api dashboard dagster-webserver dagster-daemon mlflow

compose-ps: ## Show Compose service status
	$(COMPOSE) ps

compose-test: ## Run unit/postgres tests inside Compose (profile: tools)
	$(COMPOSE) --profile tools run --rm test

compose-dbt: ## dbt deps + seed + run against Compose Postgres
	$(COMPOSE) --profile tools run --rm dbt sh -c "dbt deps && dbt seed --target dev && dbt run --target dev"

compose-dbt-test: ## dbt test against Compose Postgres
	$(COMPOSE) --profile tools run --rm dbt dbt test --target dev

compose-train-synthetic: ## Train XGBoost on synthetic features; log to Compose MLflow
	$(COMPOSE) --profile tools run --rm train

compose-train: ## Train XGBoost from feature parquet (override path via FEATURES=...)
	$(COMPOSE) --profile tools run --rm train \
		python ml/training/train_xgboost.py \
		--from-features $${FEATURES:-ml/features/datasets/lahore_aqi_features.parquet} \
		-v

dbt-deps: ## Install dbt packages on the host (dbt_utils)
	cd $(DBT_DIR) && DBT_PROFILES_DIR="$(DBT_PROFILES_DIR)" dbt deps

dbt-seed: ## Load dbt seeds (AQI breakpoints, pollutant map)
	cd $(DBT_DIR) && DBT_PROFILES_DIR="$(DBT_PROFILES_DIR)" dbt seed

dbt-run: ## Run dbt models on the host (seed + run)
	cd $(DBT_DIR) && DBT_PROFILES_DIR="$(DBT_PROFILES_DIR)" dbt seed && DBT_PROFILES_DIR="$(DBT_PROFILES_DIR)" dbt run

dbt-test: ## Run dbt tests on the host
	cd $(DBT_DIR) && DBT_PROFILES_DIR="$(DBT_PROFILES_DIR)" dbt test

dbt-freshness: ## Check raw source freshness on the host
	cd $(DBT_DIR) && DBT_PROFILES_DIR="$(DBT_PROFILES_DIR)" dbt source freshness

dagster-dev: ## Start local Dagster UI on the host (DAGSTER_HOME=orchestration/dagster)
	cd $(DAGSTER_DIR) && DAGSTER_HOME="$(CURDIR)/$(DAGSTER_DIR)" dagster dev -w workspace.yaml

db-upgrade: ## Apply Alembic migrations to head
	alembic upgrade head

db-downgrade: ## Roll back one Alembic revision
	alembic downgrade -1

db-current: ## Show current Alembic revision
	alembic current

clean: ## Remove local caches and build artifacts
	find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} + 2>/dev/null || true
