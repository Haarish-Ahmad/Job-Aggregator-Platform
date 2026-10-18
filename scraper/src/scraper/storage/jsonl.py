import json
import threading
from pathlib import Path

from scraper.models import FailedJob, JobRecord
from scraper.storage.base import Storage


class JsonlStorage(Storage):
    """Append-only JSONL. If a job changes, a new line is appended; the latest line wins."""

    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.jobs_path = directory / "jobs.jsonl"
        self.dead_letter_path = directory / "dead_letter.jsonl"
        self._lock = threading.Lock()
        self._hashes: dict[tuple[str, str], str] = {}
        self._tags: dict[tuple[str, str], str | None] = {}
        self._rows: dict[tuple[str, str], dict] = {}
        if self.jobs_path.exists():
            for line in self.jobs_path.read_text().splitlines():
                row = json.loads(line)
                key = (row["source"], row["external_id"])
                self._hashes[key] = row["content_hash"]
                self._tags[key] = self._tag_of(row.get("extraction"))
                self._rows[key] = row

    @staticmethod
    def _tag_of(extraction: dict | None) -> str | None:
        return f"{extraction['model']}|{extraction['prompt_version']}" if extraction else None

    def get_extraction_tag(self, source: str, external_id: str) -> str | None:
        return self._tags.get((source, external_id))

    def get_record(self, source: str, external_id: str) -> JobRecord | None:
        row = self._rows.get((source, external_id))
        return JobRecord.model_validate(row) if row else None

    def get_hash(self, source: str, external_id: str) -> str | None:
        return self._hashes.get((source, external_id))

    def save(self, record: JobRecord) -> None:
        with self._lock:
            with self.jobs_path.open("a") as f:
                f.write(record.model_dump_json() + "\n")
            key = (record.source, record.external_id)
            self._hashes[key] = record.content_hash
            ext = record.extraction
            self._tags[key] = f"{ext.model}|{ext.prompt_version}" if ext else None
            self._rows[key] = json.loads(record.model_dump_json())

    def save_failure(self, failure: FailedJob) -> None:
        with self._lock, self.dead_letter_path.open("a") as f:
            f.write(failure.model_dump_json() + "\n")
