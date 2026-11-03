# Build context is the repository root (requirements.txt lives there):  docker build -f backend/Dockerfile .
FROM python:3.12-slim AS build
WORKDIR /build
COPY requirements.txt .
# Generous timeouts/retries: a slow mirror should not fail the whole build.
RUN pip install --no-cache-dir --default-timeout=120 --retries=8 --prefix=/install -r requirements.txt

FROM python:3.12-slim
LABEL org.opencontainers.image.title="job-aggregator-backend"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/app \
    HF_HOME=/home/app/.cache/huggingface
COPY --from=build /install /usr/local
RUN useradd --system --uid 10001 --create-home --home-dir /home/app --shell /usr/sbin/nologin app \
    && mkdir -p "$HF_HOME" \
    && chown -R app:app /home/app
WORKDIR /app
COPY --chown=app:app backend/ /app/
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
ENTRYPOINT ["/app/docker-entrypoint.sh"]
