"""Runs inside the scraper container (docker compose exec -T scraper python - < this file).

One real pipeline run with the container's own settings: mock Firecrawl -> Shine adapter -> mock Ollama -> backend.
robots.txt checking is switched off here only because the target site is not contacted at all (Firecrawl is mocked).
"""
import sys

from scraper.config import Settings
from scraper.http import PoliteClient
from scraper.models import SearchFilters
from scraper.runner import run_source

settings = Settings()
client = PoliteClient(settings.user_agent, 0, respect_robots=False)
filters = SearchFilters(queries=["java developer fresher"], locations=["India"], limit=3)
try:
    stats, push, _ = run_source("shine", settings, client, filters, extract=True, push=True)
finally:
    client.close()
print(f"pipeline: discovered={stats.discovered} saved={stats.saved} unchanged={stats.unchanged} failed={stats.failed} "
      f"extracted={stats.extracted} | backend: {push.summary()}")
sys.exit(0 if stats.failed == 0 and push.failed == 0 and push.rejected == 0 else 1)
