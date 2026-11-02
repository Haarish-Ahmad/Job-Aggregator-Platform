from typer.testing import CliRunner

from scraper import cli
from scraper import runner as runner_module
from scraper.adapters.base import SourceAdapter
from scraper.config import Settings
from scraper.models import JobRef, RawJob
from scraper.pipeline import RunStats
from scraper.pipeline import run as run_pipeline
from scraper.storage.jsonl import JsonlStorage


class FakeAdapter(SourceAdapter):
    name, company = "fake", "Fake Co"
    TITLES = {"1": "Software Engineering Intern", "2": "Senior Software Engineer", "3": "Marketing Intern"}

    def discover(self, filters):
        return [JobRef(external_id=i, url=f"u{i}") for i in self.TITLES]

    def extract_external_id(self, url):
        return url

    def fetch(self, ref):
        return RawJob(ref=ref, content="")

    def normalize(self, raw):
        return {"title": self.TITLES[raw.ref.external_id], "employment_type": "internship",
                "description_text": f"text {raw.ref.external_id}"}


def test_pipeline_filters_before_storing(tmp_path):
    from scraper.models import SearchFilters
    adapter = FakeAdapter(client=None, settings=Settings())
    storage = JsonlStorage(tmp_path)
    stats = run_pipeline(adapter, SearchFilters(queries=[], locations=[], limit=10), storage,
                         Settings(max_concurrency=1))
    assert (stats.saved, stats.filtered) == (1, 2)
    assert len((tmp_path / "jobs.jsonl").read_text().splitlines()) == 1


def test_cli_passes_query_for_every_source(monkeypatch, tmp_path):
    seen = {}

    def fake_run(adapter, filters, storage, settings, on_record=None):
        seen["queries"] = filters.queries
        return RunStats()

    monkeypatch.setattr(runner_module, "run_pipeline", fake_run)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    runner = CliRunner()
    for source in ("microsoft", "google", "internshala", "ycombinator"):
        result = runner.invoke(cli.app, ["run", "--source", source, "--query", "my-query"])
        assert result.exit_code == 0, result.output
        assert seen["queries"] == ["my-query"], source
    runner.invoke(cli.app, ["run", "--source", "internshala"])
    assert seen["queries"][0] == "computer-science" and {"ai-ml", "cyber-security"} <= set(seen["queries"])


def test_cli_uses_each_adapters_own_default_queries(monkeypatch, tmp_path):
    from scraper.adapters import REGISTRY

    seen = {}
    monkeypatch.setattr(runner_module, "run_pipeline", lambda a, f, st, se, ex=None, on_record=None: (seen.update(q=f.queries), RunStats())[1])
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    CliRunner().invoke(cli.app, ["run", "--source", "unstop"])
    assert seen["q"] == REGISTRY["unstop"].default_queries and "software" in seen["q"]
    CliRunner().invoke(cli.app, ["run", "--source", "microsoft"])
    assert seen["q"] == Settings().query_list
    assert CliRunner().invoke(cli.app, ["run", "--source", "nope"]).exit_code != 0
