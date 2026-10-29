from abc import ABC, abstractmethod

from scraper.models import FailedJob, JobRecord


class Storage(ABC):
    """Swap JsonlStorage for a database class later without touching the pipeline."""

    @abstractmethod
    def get_hash(self, source: str, external_id: str) -> str | None:
        """Content hash of the stored record, or None if we have never stored it."""

    @abstractmethod
    def get_extraction_tag(self, source: str, external_id: str) -> str | None:
        """'model|prompt_version' of the stored record's extraction, or None if it has none."""

    @abstractmethod
    def get_record(self, source: str, external_id: str) -> JobRecord | None:
        """The latest stored record, or None."""

    @abstractmethod
    def save(self, record: JobRecord) -> None: ...

    @abstractmethod
    def save_failure(self, failure: FailedJob) -> None: ...
