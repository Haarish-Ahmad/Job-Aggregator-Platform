#!/usr/bin/env python3
"""Fail if environment variables drift between the code, docker-compose.yml and .env.example.

* every variable compose passes from .env must be documented in .env.example
* every variable in .env.example must be used (by compose, or deliberately documented as code-only below)
* every backend / scraper setting must be configurable: either passed by compose, or listed as optional below
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def env_example_keys() -> set[str]:
    keys = set()
    for line in (ROOT / ".env.example").read_text().splitlines():
        m = re.match(r"^#?\s*([A-Z][A-Z0-9_]+)=", line)
        if m:
            keys.add(m.group(1))
    return keys


def compose_vars() -> set[str]:
    """Names referenced as ${NAME...} anywhere in docker-compose.yml."""
    return set(re.findall(r"\$\{([A-Z][A-Z0-9_]+)", (ROOT / "docker-compose.yml").read_text()))


def compose_service_env(service: str) -> set[str]:
    """KEY names in a service's environment block."""
    text = (ROOT / "docker-compose.yml").read_text()
    block = re.search(rf"^  {service}:\n(.*?)(?=^  \S|\Z)", text, re.S | re.M)
    env = re.search(r"    environment:\n((?:      .*\n)+)", block.group(1)) if block else None
    return set(re.findall(r"^      ([A-Z][A-Z0-9_]+):", env.group(1), re.M)) if env else set()


def settings_fields(path: Path) -> set[str]:
    """UPPER_CASE names of the attributes of the Settings class in a config.py."""
    text = path.read_text()
    body = text[text.index("class Settings"):]
    return {m.upper() for m in re.findall(r"^    ([a-z][a-z0-9_]*)\s*:\s*[\w\[\]| .]+(?:=|\n)", body, re.M)}


# Settings that exist in code but are intentionally not exposed through compose / .env.example.
BACKEND_NOT_IN_COMPOSE = {"APP_ENV", "DATABASE_URL", "ROOT_PATH", "ALERT_MAX_JOBS_PER_EMAIL", "CURRICULUM_FILE", "IS_DEV"}
# set in compose itself or derived (not user-facing knobs)
SCRAPER_NOT_IN_COMPOSE = {"USER_AGENT", "SEARCH_QUERIES", "LOCATIONS", "OUTPUT_DIR", "MAX_MARKDOWN_CHARS",
                          "BACKEND_URL", "INGEST_BATCH_SIZE",
                          "BACKEND_TIMEOUT_SECONDS", "METRICS_PORT", "ALERTS_AFTER_RUN"}
# .env.example entries that compose does not reference by that name but are documented on purpose
EXAMPLE_ONLY = {"IMAGE_PREFIX", "IMAGE_TAG"}  # used by docker-compose.prod.yml (commented out by default)


def main() -> int:
    problems = []
    example, used = env_example_keys(), compose_vars()
    for name in sorted(used - example):
        problems.append(f"compose uses ${{{name}}} but .env.example does not document it")
    for name in sorted(example - used - EXAMPLE_ONLY):
        problems.append(f".env.example documents {name} but docker-compose.yml never reads it")

    backend_env = compose_service_env("backend")
    for name in sorted(settings_fields(ROOT / "backend" / "config.py") - backend_env - BACKEND_NOT_IN_COMPOSE):
        problems.append(f"backend setting {name} cannot be set through compose (add it, or list it as code-only in check_env.py)")
    scraper_env = compose_service_env("scraper")
    for name in sorted(settings_fields(ROOT / "scraper" / "src" / "scraper" / "config.py") - scraper_env - SCRAPER_NOT_IN_COMPOSE):
        problems.append(f"scraper setting {name} cannot be set through compose (add it, or list it as code-only in check_env.py)")

    for p in problems:
        print("FAIL", p)
    print(f"{len(example)} documented, {len(used)} used by compose, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
