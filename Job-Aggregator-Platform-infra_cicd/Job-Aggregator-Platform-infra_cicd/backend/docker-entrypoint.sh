#!/bin/sh
# Apply migrations, make sure the admin exists, then serve. Runs as a single process: the Prometheus
# client keeps its counters in memory, so more than one worker would split the numbers.
set -eu
alembic upgrade head
if [ -n "${ADMIN_EMAIL:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
    python create_admin.py
fi
exec uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'
