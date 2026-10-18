"""`scraper serve`: scrape on a schedule, push to the backend, and expose /metrics and /health.

A one-shot CLI cannot be scraped by Prometheus, so the deployed scraper is this long-running process.
"""
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from scraper.config import Settings
from scraper.http import PoliteClient
from scraper.metrics import RUN_ACTIVE
from scraper.runner import build_filters, run_source

log = logging.getLogger(__name__)


class ServeState:
    def __init__(self) -> None:
        self.cycles = 0
        self.running = False
        self.last_started: float | None = None
        self.last_finished: float | None = None
        self.last_results: dict[str, str] = {}

    def snapshot(self) -> dict:
        return {"status": "ok", "cycles": self.cycles, "running": self.running, "last_started": self.last_started,
                "last_finished": self.last_finished, "last_results": self.last_results}


def after_cycle(settings: Settings, backend_client: httpx.Client | None = None) -> None:
    """Ask the backend to retire postings that stopped appearing, then send alert emails for new matches."""
    headers = {"X-Ingest-Token": settings.ingest_token}
    client = backend_client or httpx.Client(base_url=settings.backend_url.rstrip("/"), timeout=settings.backend_timeout_seconds)
    try:
        calls = ["/internal/maintenance/deactivate-stale"] + (["/internal/alerts/run"] if settings.alerts_after_run else [])
        for path in calls:
            try:
                resp = client.post(path, headers=headers)
                log.info("%s -> HTTP %s %s", path, resp.status_code, resp.text[:200])
            except httpx.HTTPError as exc:
                log.error("%s failed: %s", path, exc)
    finally:
        if backend_client is None:
            client.close()


def run_cycle(settings: Settings, state: ServeState, backend_client: httpx.Client | None = None, runner=run_source) -> None:
    """One pass over every configured source. A failing source never stops the others."""
    state.running, state.last_started = True, time.time()
    RUN_ACTIVE.set(1)
    pushed_any = False
    try:
        for source in settings.serve_source_list:
            client = PoliteClient(settings.user_agent, settings.request_delay_seconds)
            try:
                filters = build_filters(source, settings, None, None, settings.serve_limit)
                stats, push_stats, _ = runner(source, settings, client, filters, extract=settings.serve_extract, push=True, backend_client=backend_client)
                state.last_results[source] = f"ok discovered={stats.discovered} saved={stats.saved} failed={stats.failed}" + (
                    f" push[{push_stats.summary()}]" if push_stats else "")
                pushed_any = pushed_any or bool(push_stats and (push_stats.inserted or push_stats.updated or push_stats.unchanged))
                log.info("%s: %s", source, state.last_results[source])
            except Exception as exc:
                log.exception("source %s failed", source)
                state.last_results[source] = f"error {type(exc).__name__}: {exc}"
            finally:
                client.close()
        if pushed_any:
            after_cycle(settings, backend_client)
    finally:
        state.cycles += 1
        state.running, state.last_finished = False, time.time()
        RUN_ACTIVE.set(0)


def make_handler(state: ServeState):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (stdlib name)
            if self.path == "/metrics":
                body, ctype, code = generate_latest(), CONTENT_TYPE_LATEST, 200
            elif self.path == "/health":
                body, ctype, code = json.dumps(state.snapshot()).encode(), "application/json", 200
            else:
                body, ctype, code = b"not found", "text/plain", 404
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the logs for scraping, not for every probe
            pass

    return Handler


def start_status_server(state: ServeState, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(state))  # noqa: S104 (inside a container)
    threading.Thread(target=server.serve_forever, daemon=True, name="status-server").start()
    log.info("status server on :%d (/metrics, /health)", server.server_address[1])
    return server


def serve(settings: Settings, stop: threading.Event | None = None, cycle=run_cycle) -> ServeState:
    stop = stop or threading.Event()
    state = ServeState()
    server = start_status_server(state, settings.metrics_port)
    try:
        if not settings.run_on_start and stop.wait(settings.scrape_interval_hours * 3600):
            return state
        while not stop.is_set():
            cycle(settings, state)
            if stop.wait(settings.scrape_interval_hours * 3600):
                break
    finally:
        server.shutdown()
    return state
