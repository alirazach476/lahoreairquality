# ML training / features image (one-shot jobs via Compose run).
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md ./
COPY src ./src
COPY ml/pyproject.toml ./ml/pyproject.toml
COPY ml/README.md ./ml/README.md
COPY ml/src ./ml/src

RUN pip install --no-cache-dir --prefix=/install . ./ml


FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home /app --shell /usr/sbin/nologin app

COPY --from=builder /install /usr/local
COPY --chown=app:app ml ./ml
COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app src ./src

RUN mkdir -p /app/ml/training/artifacts /app/ml/features/datasets \
    && chown -R app:app /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MLFLOW_TRACKING_URI=http://mlflow:5000

USER app

# Default: synthetic smoke train (override for real feature parquet).
CMD ["python", "ml/training/train_xgboost.py", "--synthetic", "-v"]
