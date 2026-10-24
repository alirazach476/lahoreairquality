# Ingestion poller: OpenAQ + Open-Meteo → Redpanda.
# Multi-stage: build deps as root, run as non-root.
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md ./
COPY src ./src
COPY ingestion/poller/pyproject.toml ./ingestion/poller/pyproject.toml
COPY ingestion/poller/README.md ./ingestion/poller/README.md
COPY ingestion/poller/src ./ingestion/poller/src

RUN pip install --no-cache-dir --prefix=/install . ./ingestion/poller


FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home /app --shell /usr/sbin/nologin app

COPY --from=builder /install /usr/local

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app
STOPSIGNAL SIGTERM

CMD ["python", "-m", "lahore_aqi_poller"]
