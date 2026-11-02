FROM nginxinc/nginx-unprivileged:1.27-alpine
LABEL org.opencontainers.image.title="job-aggregator-edge"
COPY default.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
