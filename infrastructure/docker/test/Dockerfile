# CI-style unit test image (no live external APIs).
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY alembic ./alembic
COPY apps/api ./apps/api
COPY ingestion ./ingestion
COPY ml ./ml
COPY orchestration/dagster ./orchestration/dagster
COPY tests ./tests

RUN pip install --no-cache-dir \
      ".[dev]" \
      ./apps/api[dev] \
      ./ingestion/poller \
      ./ingestion/consumer \
      ./ml[dev] \
      ./orchestration/dagster

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RUN_EXTERNAL_API_TESTS=0

CMD ["pytest", "-m", "not integration and not smoke", "-v", "--tb=short"]
