from abc import ABC, abstractmethod

from scraper.config import Settings
from scraper.http import PoliteClient
from scraper.models import JobRef, RawJob, SearchFilters


class SourceAdapter(ABC):
    """One career site = one subclass. The pipeline only ever talks to this interface.

    How a site is fetched (JSON API, Firecrawl, ...) is the adapter's private business.
    """

    name: str
    company: str
    # True when the source's own listing is already limited to software roles.
    software_trusted: bool = False
    # True for job boards that only list Indian opportunities, so a posting with a place that is not
    # recognisably Indian (a small town) is still treated as being in India.
    india_portal: bool = False
    # Used when the CLI gets no --query. None means fall back to SEARCH_QUERIES from settings.
    default_queries: list[str] | None = None

    def __init__(self, client: PoliteClient, settings: Settings):
        self.client = client
        self.settings = settings

    @abstractmethod
    def discover(self, filters: SearchFilters) -> list[JobRef]:
        """Find postings matching the filters (at most filters.limit)."""

    @abstractmethod
    def extract_external_id(self, url: str) -> str:
        """Stable id of a posting, taken from its URL."""

    @abstractmethod
    def fetch(self, ref: JobRef) -> RawJob:
        """Download one posting's content."""

    @abstractmethod
    def normalize(self, raw: RawJob) -> dict:
        """Turn raw content into JobRecord fields.

        Must NOT include the code-controlled fields (source, company, url, external_id,
        scraped_at, content_hash): the pipeline sets those.
        """
