"""The pipeline counters Prometheus scrapes from `scraper serve`."""
from prometheus_client import REGISTRY

from scraper.config import Settings
from scraper.models import SearchFilters
from scraper.pipeline import run as run_pipeline
from scraper.storage.jsonl import JsonlStorage
from tests.test_pipeline_filter_and_cli import FakeAdapter


def sample(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_a_run_counts_pages_and_job_outcomes(tmp_path):
    before = {k: sample(*k[0], **dict(k[1])) for k in [
        (("scraper_pages_total",), (("source", "fake"), ("outcome", "ok"))),
        (("scraper_jobs_total",), (("source", "fake"), ("outcome", "saved"))),
        (("scraper_jobs_total",), (("source", "fake"), ("outcome", "filtered"))),
    ]}
    adapter = FakeAdapter(client=None, settings=Settings())
    run_pipeline(adapter, SearchFilters(queries=[], locations=[], limit=10), JsonlStorage(tmp_path), Settings(max_concurrency=1))
    assert sample("scraper_pages_total", source="fake", outcome="ok") - before[(("scraper_pages_total",), (("source", "fake"), ("outcome", "ok")))] == 3
    assert sample("scraper_jobs_total", source="fake", outcome="saved") - before[(("scraper_jobs_total",), (("source", "fake"), ("outcome", "saved")))] == 1
    assert sample("scraper_jobs_total", source="fake", outcome="filtered") - before[(("scraper_jobs_total",), (("source", "fake"), ("outcome", "filtered")))] == 2


def test_failed_fetches_are_counted_not_fatal(tmp_path):
    class Broken(FakeAdapter):
        name = "broken"

        def fetch(self, ref):
            raise RuntimeError("site down")

    start = (sample("scraper_pages_total", source="broken", outcome="error"), sample("scraper_jobs_total", source="broken", outcome="failed"))
    stats = run_pipeline(Broken(client=None, settings=Settings()), SearchFilters(queries=[], locations=[], limit=10),
                         JsonlStorage(tmp_path), Settings(max_concurrency=1))
    assert stats.failed == 3
    assert sample("scraper_pages_total", source="broken", outcome="error") - start[0] == 3
    assert sample("scraper_jobs_total", source="broken", outcome="failed") - start[1] == 3


def test_run_source_records_duration_and_last_success(tmp_path, monkeypatch):
    from scraper import runner

    monkeypatch.setitem(runner.REGISTRY, "fake", FakeAdapter)
    settings = Settings(output_dir=tmp_path, max_concurrency=1)
    runs_before = sample("scraper_runs_total", source="fake", result="ok")
    runner.run_source("fake", settings, client=None, filters=SearchFilters(queries=[], locations=[], limit=5))
    assert sample("scraper_runs_total", source="fake", result="ok") - runs_before == 1
    assert sample("scraper_run_duration_seconds_count", source="fake") >= 1
    assert sample("scraper_last_success_timestamp_seconds", source="fake") > 1.7e9
