"""Prometheus metrics: HTTP request counters/latency per route template, ingest outcomes, DB-backed gauges."""
import logging
import time

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily
from fastapi import Response
from sqlalchemy import func, select
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "route"],
                    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
ERRORS = Counter("http_server_errors_total", "HTTP responses with a 5xx status", ["route"])
INGEST_RECORDS = Counter("ingest_records_total", "Records received by /internal/jobs", ["status"])
ALERT_EMAILS = Counter("alert_emails_total", "Alert emails by result", ["result"])


class MetricsMiddleware:
    """Pure ASGI middleware. Labels use the matched route template (/jobs/{job_id}), never the raw path."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].endswith("/metrics"):
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            method = scope["method"]
            REQUESTS.labels(method, route, str(status["code"])).inc()
            LATENCY.labels(method, route).observe(time.perf_counter() - start)
            if status["code"] >= 500:
                ERRORS.labels(route).inc()


class DatabaseGauges:
    """Gauges computed from the database at scrape time (so they are always current)."""

    def collect(self):
        from db import session_local
        from models import Job, Students

        jobs = GaugeMetricFamily("jobs_active", "Active job postings by source", labels=["source"])
        students = GaugeMetricFamily("students_total", "Registered students")
        try:
            with session_local() as db:
                source_col = func.coalesce(Job.source, "manual").label("source")
                for source, n in db.execute(
                    select(source_col, func.count()).where(Job.is_active.is_(True)).group_by(source_col)
                ):
                    jobs.add_metric([source], n)
                students.add_metric([], db.scalar(select(func.count()).select_from(Students)) or 0)
        except Exception:  # the DB being down must not break /metrics (the health check reports it)
            log.warning("could not read database gauges for /metrics", exc_info=True)
        yield jobs
        yield students


REGISTRY.register(DatabaseGauges())


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
