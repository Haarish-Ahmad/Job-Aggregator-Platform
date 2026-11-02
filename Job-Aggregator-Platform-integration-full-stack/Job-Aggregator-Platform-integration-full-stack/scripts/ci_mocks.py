#!/usr/bin/env python3
"""Stand-in for Firecrawl (:3002) so the stack can be tested without a real one.

POST /v2/scrape -> Shine fixture markdown (search page or job page, by URL).
Listens on all interfaces so containers reach it through host.docker.internal.
Port: MOCK_FIRECRAWL_PORT (default 3002); the smoke test picks a free one because a real Firecrawl often
occupies the default on a developer machine.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "scraper" / "fixtures"
LISTING = (FIXTURES / "shine_listing.md").read_text()
DETAIL = (FIXTURES / "shine_detail.md").read_text()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        self._send(200, {"status": "mock"})

    def do_POST(self):  # noqa: N802
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        if self.path == "/v2/scrape":
            markdown = LISTING if "/job-search/" in payload.get("url", "") else DETAIL
            self._send(200, {"success": True, "data": {"markdown": markdown}})
        else:
            self._send(404, {"error": "not mocked"})

    def log_message(self, *args):
        pass


def main() -> None:
    port = int(os.environ.get("MOCK_FIRECRAWL_PORT", 3002))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)  # noqa: S104
    print(f"mock Firecrawl on :{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
