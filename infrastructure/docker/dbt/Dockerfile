# One-shot / interactive dbt image (seed, run, test against Compose Postgres).
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --prefix=/install ".[dbt]"


FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home /app --shell /usr/sbin/nologin app

COPY --from=builder /install /usr/local
COPY --chown=app:app dbt/lahore_air_quality ./dbt/lahore_air_quality

WORKDIR /app/dbt/lahore_air_quality

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DBT_PROFILES_DIR=/app/dbt/lahore_air_quality \
    DBT_PROJECT_DIR=/app/dbt/lahore_air_quality

USER app

# Callers should run `dbt deps` before seed/run/test (see Makefile compose-dbt*).
CMD ["dbt", "run", "--target", "dev"]
