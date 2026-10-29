"""What the pipeline hands to the consumer (the backend pusher) for saved and unchanged jobs."""
from datetime import UTC, datetime

from scraper.adapters.base import SourceAdapter
from scraper.config import Settings
from scraper.models import ExtractionResult, JobExtraction, JobRef, RawJob, SearchFilters
from scraper.pipeline import run as run_pipeline
from scraper.storage.jsonl import JsonlStorage


class Adapter(SourceAdapter):
    name, company = "fake", "Fake Co"
    employer = "Acme"

    def discover(self, filters):
        return [JobRef(external_id="1", url="u1")]

    def extract_external_id(self, url):
        return url

    def fetch(self, ref):
        return RawJob(ref=ref, content="")

    def normalize(self, raw):
        return {"title": "Software Engineering Intern", "company": self.employer, "employment_type": "internship",
                "description_text": "the same text every run"}


FILTERS = SearchFilters(queries=[], locations=[], limit=5)


def run(tmp_path, adapter, storage=None, extractor=None):
    delivered = []
    storage = storage or JsonlStorage(tmp_path)
    stats = run_pipeline(adapter, FILTERS, storage, Settings(max_concurrency=1), extractor, on_record=delivered.append)
    return stats, delivered, storage


def test_saved_and_unchanged_jobs_are_both_delivered(tmp_path):
    adapter = Adapter(client=None, settings=Settings())
    first, delivered1, storage = run(tmp_path, adapter)
    second, delivered2, _ = run(tmp_path, adapter, storage)
    assert (first.saved, second.unchanged) == (1, 1)
    assert len(delivered1) == 1 and len(delivered2) == 1


def test_an_unchanged_job_is_delivered_with_its_freshly_parsed_fields(tmp_path):
    """A parser fix (here: a different employer) must reach the consumer even though the text did not change."""
    adapter = Adapter(client=None, settings=Settings())
    _, _, storage = run(tmp_path, adapter)
    adapter.employer = "Acme Corporation"
    stats, delivered, _ = run(tmp_path, adapter, storage)
    assert stats.unchanged == 1 and delivered[0].company == "Acme Corporation"


def test_an_unchanged_job_keeps_the_extraction_already_stored(tmp_path):
    adapter = Adapter(client=None, settings=Settings())
    _, _, storage = run(tmp_path, adapter)
    stored = storage.get_record("fake", "1")
    stored.extraction = ExtractionResult(model="m", prompt_version="1", extracted_at=datetime.now(UTC), data=JobExtraction(skills=["Rust"]))
    storage.save(stored)
    stats, delivered, _ = run(tmp_path, adapter, storage)
    assert stats.unchanged == 1 and delivered[0].extraction.data.skills == ["Rust"]


def test_filtered_and_failed_jobs_are_not_delivered(tmp_path):
    class Mixed(Adapter):
        def discover(self, filters):
            return [JobRef(external_id=i, url=i) for i in ("1", "2", "3")]

        def fetch(self, ref):
            if ref.external_id == "3":
                raise RuntimeError("down")
            return RawJob(ref=ref, content="")

        def normalize(self, raw):
            title = "Marketing Intern" if raw.ref.external_id == "2" else "Software Engineering Intern"
            return {"title": title, "employment_type": "internship", "description_text": "x"}

    stats, delivered, _ = run(tmp_path, Mixed(client=None, settings=Settings()))
    assert (stats.saved, stats.filtered, stats.failed) == (1, 1, 1) and [r.external_id for r in delivered] == ["1"]
