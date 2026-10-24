# Dagster orchestration (webserver + daemon share this image).
# Includes poller/consumer CLIs and dbt-postgres for pipeline stages.
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md ./
COPY src ./src
COPY ingestion/poller ./ingestion/poller
COPY ingestion/consumer ./ingestion/consumer
COPY orchestration/dagster/pyproject.toml ./orchestration/dagster/pyproject.toml
COPY orchestration/dagster/README.md ./orchestration/dagster/README.md
COPY orchestration/dagster/src ./orchestration/dagster/src

RUN pip install --no-cache-dir --prefix=/install \
      ".[orchestration,dbt]" \
      ./ingestion/poller \
      ./ingestion/consumer \
      ./orchestration/dagster


FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home /app --shell /usr/sbin/nologin app

COPY --from=builder /install /usr/local

# Repo layout required for DBT_* path defaults and workspace loading.
COPY --chown=app:app pyproject.toml README.md alembic.ini ./
COPY --chown=app:app src ./src
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app ingestion ./ingestion
COPY --chown=app:app orchestration/dagster ./orchestration/dagster
COPY --chown=app:app dbt ./dbt

WORKDIR /app/orchestration/dagster

RUN mkdir -p /app/orchestration/dagster/.dagster_home \
    && chown -R app:app /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DAGSTER_HOME=/app/orchestration/dagster \
    DBT_PROJECT_DIR=/app/dbt/lahore_air_quality \
    DBT_PROFILES_DIR=/app/dbt/lahore_air_quality

USER app
EXPOSE 3000

# Default: webserver. Compose overrides command for the daemon.
CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-w", "workspace.yaml"]
