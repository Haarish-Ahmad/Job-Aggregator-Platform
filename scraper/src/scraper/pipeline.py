import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

from scraper.adapters.base import SourceAdapter
from scraper.config import Settings
from scraper.metrics import JOBS, PAGES
from scraper.models import FailedJob, JobRecord, JobRef, SearchFilters
from scraper.preprocess import content_hash
from scraper.relevance import assess, min_years_from_items
from scraper.storage.base import Storage

log = logging.getLogger(__name__)


@dataclass
class RunStats:
    discovered: int = 0
    saved: int = 0
    unchanged: int = 0
    filtered: int = 0
    failed: int = 0


def build_record(adapter: SourceAdapter, raw, now: datetime) -> JobRecord:
    """Normalize adapter output and attach the fields that code (not the source) controls."""
    fields = adapter.normalize(raw)
    if fields.get("min_experience_years") is None:
        fields["min_experience_years"] = min_years_from_items(fields.get("required_qualifications", []))
    return JobRecord(
        source=adapter.name,
        company=fields.pop("company", None) or adapter.company,
        external_id=raw.ref.external_id,
        url=raw.ref.url,
        scraped_at=now,
        content_hash=content_hash(fields["description_text"]),
        **fields,
    )


def process_job(
    adapter: SourceAdapter,
    ref: JobRef,
    storage: Storage,
    stats: RunStats | None = None,
    on_record: Callable[[JobRecord], None] | None = None,
) -> str:
    """Fetch -> normalize -> filter -> store one job.

    Returns 'saved', 'unchanged' or 'filtered'. Raises on fetch/normalize failure.

    on_record receives the record to deliver downstream for every job that is 'saved' or 'unchanged'. For an
    unchanged job that is the freshly parsed record, so a parser fix reaches the consumer without a new posting.
    """
    stats = stats or RunStats()
    try:
        raw = adapter.fetch(ref)
    except Exception:
        PAGES.labels(adapter.name, "error").inc()
        raise
    PAGES.labels(adapter.name, "ok").inc()
    record = build_record(adapter, raw, datetime.now(UTC))
    verdict = assess(record, software_trusted=adapter.software_trusted)
    if not verdict.ok:
        log.info("filtered out %r (%s)", record.title, verdict.reason)
        return "filtered"
    if storage.get_hash(record.source, record.external_id) == record.content_hash:
        if on_record:
            on_record(record)
        return "unchanged"  # same text as the stored copy: nothing new to store
    storage.save(record)
    if on_record:
        on_record(record)
    return "saved"


def run(
    adapter: SourceAdapter,
    filters: SearchFilters,
    storage: Storage,
    settings: Settings,
    on_record: Callable[[JobRecord], None] | None = None,
) -> RunStats:
    """on_record(record) is called for every job that ends 'saved' or 'unchanged' (e.g. to push it on)."""
    stats = RunStats()
    refs = adapter.discover(filters)
    stats.discovered = len(refs)
    log.info("discovered %d jobs from %s", len(refs), adapter.name)

    def work(ref: JobRef) -> None:
        try:
            outcome = process_job(adapter, ref, storage, stats, on_record)
            setattr(stats, outcome, getattr(stats, outcome) + 1)
            JOBS.labels(adapter.name, outcome).inc()
        except Exception as exc:  # one bad URL must not abort the run
            log.error("failed %s: %s", ref.url, exc)
            JOBS.labels(adapter.name, "failed").inc()
            stats.failed += 1
            storage.save_failure(
                FailedJob(
                    source=adapter.name,
                    external_id=ref.external_id,
                    url=ref.url,
                    stage="fetch_or_normalize",
                    error=f"{type(exc).__name__}: {exc}",
                    at=datetime.now(UTC),
                )
            )

    with ThreadPoolExecutor(max_workers=settings.max_concurrency) as pool:
        list(pool.map(work, refs))
    return stats
