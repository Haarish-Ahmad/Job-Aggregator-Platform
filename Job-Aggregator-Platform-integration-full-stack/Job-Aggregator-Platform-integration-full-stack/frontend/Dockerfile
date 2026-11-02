# --- build: install from the lockfile, type-check and bundle
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# --- run: static files behind an unprivileged nginx (uid 101, port 8080)
FROM nginxinc/nginx-unprivileged:1.27-alpine
LABEL org.opencontainers.image.title="job-aggregator-frontend"
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Owned by the unprivileged nginx user so the entrypoint can write config.js without root.
COPY --chown=101:101 --from=build /app/dist /usr/share/nginx/html
# Runs before nginx starts: writes config.js from API_BASE so one image works against any API URL.
COPY --chmod=755 docker-entrypoint.sh /docker-entrypoint.d/40-runtime-config.sh
ENV API_BASE=/api
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
