FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/home/app HF_HOME=/models
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries=8 -r requirements.txt
COPY . .
RUN useradd --system --uid 10001 --home-dir /home/app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/resumes /models \
    && chmod 755 /app/docker-entrypoint.sh \
    && chown -R app:app /app /home/app /models

USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
ENTRYPOINT ["/app/docker-entrypoint.sh"]
