# MLflow tracking server (file backend + local artifact volume).
# File store avoids SQLAlchemy version conflicts with newer wheels.
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install \
      "mlflow>=2.14,<2.20" \
      "sqlalchemy>=2.0,<2.1"


FROM python:3.12-slim-bookworm AS runtime

WORKDIR /mlflow

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home /mlflow --shell /usr/sbin/nologin app \
    && mkdir -p /mlflow/artifacts /mlflow/db \
    && chown -R app:app /mlflow

COPY --from=builder /install /usr/local

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MLFLOW_BACKEND_STORE_URI=file:///mlflow/db \
    MLFLOW_DEFAULT_ARTIFACT_ROOT=/mlflow/artifacts \
    MLFLOW_HOST=0.0.0.0 \
    MLFLOW_PORT=5000

USER app
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=8 \
  CMD curl -fsS "http://127.0.0.1:${MLFLOW_PORT}/" || exit 1

CMD ["sh", "-c", "mlflow server --host \"${MLFLOW_HOST}\" --port \"${MLFLOW_PORT}\" --backend-store-uri \"${MLFLOW_BACKEND_STORE_URI}\" --default-artifact-root \"${MLFLOW_DEFAULT_ARTIFACT_ROOT}\""]
