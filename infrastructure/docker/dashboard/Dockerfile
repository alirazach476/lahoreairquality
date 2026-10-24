# React dashboard — multi-stage: Node build → nginx static serve.
FROM node:22-alpine AS build

WORKDIR /app

COPY apps/dashboard/package.json apps/dashboard/package-lock.json ./
RUN npm ci

COPY apps/dashboard/ ./

# Browser calls the API on the host-mapped port (not the Compose service name).
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build


FROM nginx:1.27-alpine AS runtime

RUN addgroup -g 10001 -S app \
    && adduser -S -D -H -u 10001 -G app app \
    && mkdir -p /var/cache/nginx /var/run \
    && chown -R app:app /var/cache/nginx /var/run /usr/share/nginx/html

COPY infrastructure/docker/dashboard/nginx.conf /etc/nginx/nginx.conf
COPY --from=build --chown=app:app /app/dist /usr/share/nginx/html

USER app
EXPOSE 8080

HEALTHCHECK --interval=20s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
