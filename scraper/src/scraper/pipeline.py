import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

from scraper.adapters.base import SourceAdapter
from scraper.config import Settings
from scraper.extraction import OllamaExtractor
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
    extracted: int = 0
    extraction_failed: int = 0
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
    extractor: OllamaExtractor | None = None,
    stats: RunStats | None = None,
) -> str:
    """Fetch -> normalize -> filter -> (LLM extract) -> store one job.

    Returns 'saved', 'unchanged' or 'filtered'. Raises on fetch/normalize failure; an extraction
    failure never loses the job, it is saved without LLM fields and retried on the next run.
    """
    stats = stats or RunStats()
    raw = adapter.fetch(ref)
    record = build_record(adapter, raw, datetime.now(UTC))
    verdict = assess(record, software_trusted=adapter.software_trusted)
    if not verdict.ok:
        log.info("filtered out %r (%s)", record.title, verdict.reason)
        return "filtered"
    unchanged = storage.get_hash(record.source, record.external_id) == record.content_hash
    needs_extraction = (
        extractor is not None
        and extractor.wants(record.description_text)
        and storage.get_extraction_tag(record.source, record.external_id) != extractor.tag
    )
    if unchanged and not needs_extraction:
        return "unchanged"  # same text and already extracted by this model/prompt: skip the LLM too
    if needs_extraction:
        try:
            record.extraction = extractor.extract(record.title, record.description_text)
            stats.extracted += 1
        except Exception as exc:
            log.error("extraction failed for %r: %s", record.title, exc)
            stats.extraction_failed += 1
            storage.save_failure(
                FailedJob(
                    source=record.source,
                    external_id=record.external_id,
                    url=record.url,
                    stage="extraction",
                    error=f"{type(exc).__name__}: {exc}",
                    at=datetime.now(UTC),
                )
            )
            if unchanged:
                return "unchanged"  # nothing new to store; retry next run
    storage.save(record)
    return "saved"


def run(
    adapter: SourceAdapter,
    filters: SearchFilters,
    storage: Storage,
    settings: Settings,
    extractor: OllamaExtractor | None = None,
) -> RunStats:
    stats = RunStats()
    refs = adapter.discover(filters)
    stats.discovered = len(refs)
    log.info("discovered %d jobs from %s", len(refs), adapter.name)

    def work(ref: JobRef) -> None:
        try:
            outcome = process_job(adapter, ref, storage, extractor, stats)
            setattr(stats, outcome, getattr(stats, outcome) + 1)
        except Exception as exc:  # one bad URL must not abort the run
            log.error("failed %s: %s", ref.url, exc)
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
