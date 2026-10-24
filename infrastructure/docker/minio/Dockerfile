# MinIO server from official binary (avoids Docker Hub / Quay pull restrictions).
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL -o /usr/local/bin/minio \
         https://dl.min.io/server/minio/release/linux-amd64/minio \
    && chmod +x /usr/local/bin/minio \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data \
    && useradd --system --uid 10001 --home /data --shell /usr/sbin/nologin minio \
    && chown -R minio:minio /data

USER minio
EXPOSE 9000 9001
VOLUME ["/data"]

ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
