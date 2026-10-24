# FastAPI backend for Lahore AQI.
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md ./
COPY src ./src
COPY apps/api/pyproject.toml ./apps/api/pyproject.toml
COPY apps/api/README.md ./apps/api/README.md
COPY apps/api/src ./apps/api/src

RUN pip install --no-cache-dir --prefix=/install . ./apps/api


FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home /app --shell /usr/sbin/nologin app

COPY --from=builder /install /usr/local

# Forecast artifact dir (populated via volume or train job).
RUN mkdir -p /app/ml/training/artifacts/xgboost \
    && chown -R app:app /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    FORECAST_ARTIFACT_DIR=/app/ml/training/artifacts/xgboost

USER app
EXPOSE 8000
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=20s --timeout=5s --start-period=25s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${API_PORT}/health" || exit 1

CMD ["lahore-aqi-api"]
