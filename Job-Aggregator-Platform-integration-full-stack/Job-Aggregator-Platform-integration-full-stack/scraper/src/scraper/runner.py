"""Run one source end to end: discover -> fetch -> normalize -> store, optionally pushing to the backend."""
import logging
import time

import httpx

from scraper.adapters import REGISTRY, get_adapter
from scraper.config import Settings
from scraper.http import PoliteClient
from scraper.metrics import LAST_SUCCESS, RUN_DURATION, RUNS
from scraper.models import SearchFilters
from scraper.pipeline import RunStats
from scraper.pipeline import run as run_pipeline
from scraper.push import BackendPusher, PushStats
from scraper.storage.jsonl import JsonlStorage

log = logging.getLogger(__name__)


def build_filters(source: str, settings: Settings, query: list[str] | None, location: list[str] | None, limit: int) -> SearchFilters:
    return SearchFilters(
        queries=query or REGISTRY[source].default_queries or settings.query_list,
        locations=location or settings.location_list,
        limit=limit,
    )


def run_source(
    source: str,
    settings: Settings,
    client: PoliteClient,
    filters: SearchFilters,
    *,
    push: bool = False,
    backend_client: httpx.Client | None = None,
) -> tuple[RunStats, PushStats | None, JsonlStorage]:
    """One scrape run. With push=True every saved or unchanged job is also sent to the backend, which
    decides inserted / updated / unchanged (and refreshes last_seen_at). Raises only for setup errors;
    individual jobs that fail are counted, never fatal."""
    started = time.perf_counter()
    adapter = get_adapter(source, client=client, settings=settings)
    storage = JsonlStorage(settings.output_dir)
    pusher = BackendPusher(settings, storage, client=backend_client, india_portal=adapter.india_portal) if push else None

    try:
        stats = run_pipeline(adapter, filters, storage, settings, on_record=pusher.add if pusher else None)
        push_stats = pusher.flush() if pusher else None
    except Exception:
        RUNS.labels(source, "error").inc()
        raise
    finally:
        RUN_DURATION.labels(source).observe(time.perf_counter() - started)
        if pusher and backend_client is None:
            pusher.close()
    RUNS.labels(source, "ok").inc()
    LAST_SUCCESS.labels(source).set_to_current_time()
    return stats, push_stats, storage
