FROM python:3.12-slim AS build
WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --default-timeout=120 --retries=8 --prefix=/install .

FROM python:3.12-slim
LABEL org.opencontainers.image.title="job-aggregator-scraper"
ENV PYTHONUNBUFFERED=1 OUTPUT_DIR=/data METRICS_PORT=9100
COPY --from=build /install /usr/local
# Run as an unprivileged user; /data holds the JSONL cache and dead-letter file (a volume in compose).
RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin scraper \
    && mkdir /data && chown scraper /data
USER scraper
VOLUME /data
EXPOSE 9100
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('METRICS_PORT','9100'), timeout=3)"
ENTRYPOINT ["scraper"]
CMD ["serve"]
