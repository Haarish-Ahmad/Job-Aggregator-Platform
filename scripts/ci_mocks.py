#!/usr/bin/env python3
"""Stand-ins for Firecrawl (:3002) and Ollama (:11434) so the stack can be tested without either.

Firecrawl: POST /v2/scrape -> Shine fixture markdown (search page or job page, by URL).
Ollama:    POST /api/chat  -> a fixed extraction; GET /api/tags -> an empty model list.
Listens on all interfaces so containers reach it through host.docker.internal.
Ports: MOCK_FIRECRAWL_PORT (default 3002) and MOCK_OLLAMA_PORT (default 11434); the smoke test picks free ones
because a real Firecrawl/Ollama often occupies the defaults on a developer machine.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "scraper" / "fixtures"
LISTING = (FIXTURES / "shine_listing.md").read_text()
DETAIL = (FIXTURES / "shine_detail.md").read_text()
EXTRACTION = {"skills": ["Java", "Python"], "graduation_years": [2026], "work_mode": "remote"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        self._send(200, {"models": []} if self.path == "/api/tags" else {"status": "mock"})

    def do_POST(self):  # noqa: N802
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        if self.path == "/v2/scrape":
            markdown = LISTING if "/job-search/" in payload.get("url", "") else DETAIL
            self._send(200, {"success": True, "data": {"markdown": markdown}})
        elif self.path == "/api/chat":
            self._send(200, {"message": {"content": json.dumps(EXTRACTION)}})
        else:
            self._send(404, {"error": "not mocked"})

    def log_message(self, *args):
        pass


def main() -> None:
    ports = (int(os.environ.get("MOCK_FIRECRAWL_PORT", 3002)), int(os.environ.get("MOCK_OLLAMA_PORT", 11434)))
    servers = [ThreadingHTTPServer(("0.0.0.0", port), Handler) for port in ports]  # noqa: S104
    for server in servers[1:]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"mock Firecrawl on :{ports[0]}, mock Ollama on :{ports[1]}", flush=True)
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
