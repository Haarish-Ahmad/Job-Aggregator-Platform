import logging
import re
import threading
import time
from urllib.parse import urlparse

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)


class RobotsDisallowed(Exception):
    pass


class RetryableHTTPError(Exception):
    """429 / 5xx responses: worth trying again after a pause."""


def _parse_robots(text: str) -> list[tuple[bool, str]]:
    """Return (allow, path_prefix) rules for the '*' user-agent group."""
    rules: list[tuple[bool, str]] = []
    in_star_group = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            in_star_group = value == "*"
        elif in_star_group and key in ("allow", "disallow") and value:
            rules.append((key == "allow", value))
    return rules


def _rule_regex(prefix: str) -> re.Pattern:
    # robots patterns: '*' matches anything, a trailing '$' anchors the end of the path.
    anchored = prefix.endswith("$")
    body = re.escape(prefix[:-1] if anchored else prefix).replace(r"\*", ".*")
    return re.compile(body + ("$" if anchored else ""))


def _path_allowed(rules: list[tuple[bool, str]], path: str) -> bool:
    # Longest matching rule wins (Google's behaviour). Python's built-in robotparser
    # uses first-match and has no wildcard support, which wrongly blocks Microsoft
    # ("Disallow: /" comes first) and ignores Internshala's "/*?*" rules.
    best_len, allowed = -1, True
    for allow, prefix in rules:
        if _rule_regex(prefix).match(path):
            length = len(prefix.rstrip("$"))
            if length > best_len or (length == best_len and allow):
                best_len, allowed = length, allow  # on a length tie, Allow wins
    return allowed


class PoliteClient:
    """httpx wrapper: robots.txt check, minimum delay between requests, retry with backoff."""

    def __init__(self, user_agent: str, delay_seconds: float = 1.5, respect_robots: bool = True):
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=30,
            follow_redirects=True,
        )
        self._delay = delay_seconds
        self._respect_robots = respect_robots
        self._lock = threading.Lock()
        self._next_allowed = 0.0
        self._robots: dict[str, list[tuple[bool, str]]] = {}

    def _check_robots(self, url: str) -> None:
        if not self._respect_robots:
            return
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            try:
                resp = self._client.get(f"{origin}/robots.txt")
                self._robots[origin] = _parse_robots(resp.text) if resp.status_code == 200 else []
            except httpx.HTTPError:
                self._robots[origin] = []
        if not _path_allowed(self._robots[origin], parts.path or "/"):
            raise RobotsDisallowed(f"robots.txt disallows {url}")

    def _wait_turn(self) -> None:
        # One shared clock so concurrent workers still space their requests out.
        with self._lock:
            now = time.monotonic()
            wait = self._next_allowed - now
            self._next_allowed = max(now, self._next_allowed) + self._delay
        if wait > 0:
            time.sleep(wait)

    @retry(
        retry=retry_if_exception_type((RetryableHTTPError, httpx.TransportError)),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )
    def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        self._wait_turn()
        resp = self._client.request(method, url, **kwargs)
        if resp.status_code == 429 or resp.status_code >= 500:
            raise RetryableHTTPError(f"{resp.status_code} from {url}")
        resp.raise_for_status()
        return resp

    def request(
        self, method: str, url: str, *, robots_target: str | None = None, **kwargs
    ) -> httpx.Response:
        # robots_target: the site we are really fetching, when `url` is a proxy like Firecrawl.
        self._check_robots(robots_target or url)
        return self._send(method, url, **kwargs)

    def get_json(self, url: str, **kwargs) -> dict:
        return self.request("GET", url, **kwargs).json()

    def close(self) -> None:
        self._client.close()
