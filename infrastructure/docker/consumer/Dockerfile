# Ingestion consumer: Redpanda → S3/MinIO + PostgreSQL.
# Also used for one-shot Alembic migrations.
# Multi-stage: build deps as root, run as non-root.
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY alembic ./alembic
COPY ingestion/consumer/pyproject.toml ./ingestion/consumer/pyproject.toml
COPY ingestion/consumer/README.md ./ingestion/consumer/README.md
COPY ingestion/consumer/src ./ingestion/consumer/src

RUN pip install --no-cache-dir --prefix=/install . ./ingestion/consumer


FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home /app --shell /usr/sbin/nologin app

COPY --from=builder /install /usr/local
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app src ./src
COPY --chown=app:app pyproject.toml README.md ./

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app
STOPSIGNAL SIGTERM

CMD ["python", "-m", "lahore_aqi_consumer"]
