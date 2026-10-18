"""fixture markdown -> Shine adapter -> mocked Ollama -> push -> backend ingest -> queryable through the API."""
import json
from pathlib import Path

import httpx
import pytest

from scraper.config import Settings
from scraper.extraction import OllamaExtractor
from scraper.models import SearchFilters
from scraper.runner import run_source

FIXTURES = Path(__file__).resolve().parents[2] / "scraper" / "fixtures"
DETAIL_URL = "https://www.shine.com/jobs/associate-software-developer-fresher-wfh-pune/recruit-crm/19485428"


class FakeFirecrawl:
    """Stands in for PoliteClient + Firecrawl: answers /v2/scrape with fixture markdown."""

    def __init__(self, detail_markdown: str | None = None):
        self.detail = detail_markdown or (FIXTURES / "shine_detail.md").read_text()
        self.listing = (FIXTURES / "shine_listing.md").read_text()
        self.scraped: list[str] = []

    def request(self, method, url, *, robots_target=None, json=None, **kwargs):
        target = json["url"]
        self.scraped.append(target)
        markdown = self.detail if "/jobs/" in target else self.listing
        return httpx.Response(200, json={"success": True, "data": {"markdown": markdown}}, request=httpx.Request(method, url))

    def close(self):
        pass


def mocked_ollama(calls: list, skills=("Java", "Python", "Kubernetes")):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content)["messages"][-1]["content"][:60])
        reply = {"skills": list(skills), "graduation_years": [2026, 2027], "work_mode": "remote"}
        return httpx.Response(200, json={"message": {"content": json.dumps(reply)}})

    settings = Settings(_env_file=None)
    return OllamaExtractor(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, output_dir=tmp_path, ingest_token="test-ingest-token", ingest_batch_size=50,
                    request_delay_seconds=0, max_concurrency=1)


FILTERS = SearchFilters(queries=["java developer fresher"], locations=["India"], limit=2)


def scrape(settings, backend, firecrawl=None, extractor=None):
    return run_source("shine", settings, firecrawl or FakeFirecrawl(), FILTERS, extract=True, push=True,
                      backend_client=backend, extractor=extractor or mocked_ollama([]))


def test_scraped_job_ends_up_queryable_through_the_api(settings, backend, student):
    ollama_calls: list = []
    stats, push, _ = scrape(settings, backend, extractor=mocked_ollama(ollama_calls))
    assert stats.saved == 2 and stats.extracted == 2 and stats.failed == 0
    assert push.inserted == 2 and push.rejected == 0 and push.failed == 0 and len(ollama_calls) == 2

    jobs = student.get("/jobs", params={"source": "shine"}).json()
    assert len(jobs) == 2 and student.get("/jobs", params={"source": "shine"}).headers["x-total-count"] == "2"
    job = next(j for j in jobs if j["external_id"] == "19485428")
    assert job["title"].startswith("Associate Software Developer Fresher")
    assert job["company_name"] == "Recruit CRM"
    assert job["apply_url"] == DETAIL_URL
    assert job["source"] == "shine" and job["job_type"] == "full_time"
    # From the (mocked) LLM, lowercased by the backend. "Kubernetes" is not in the posting text, so the
    # scraper's grounding check dropped it before it could reach the platform.
    assert job["necessary_skills"] == ["java", "python"]
    assert job["allowed_grads"] == [2026]  # 2027 is not in the posting text, so grounding dropped it
    assert job["is_remote"] is True and job["work_mode"] == "remote"  # WFH posting
    assert job["is_india"] is True and "Pune" in job["location"]
    assert job["scraped_at"] and job["last_seen_at"]
    assert student.get(f"/jobs/{job['id']}").json()["id"] == job["id"]

    # The student's profile (python) now matches it.
    matches = student.get("/me/matches").json()
    assert any(m["job"]["external_id"] == "19485428" and m["score"] > 0 for m in matches)


def test_scope_filter_finds_it_as_india_or_remote(settings, backend, student):
    scrape(settings, backend)
    assert len(student.get("/jobs", params={"scope": "india_remote"}).json()) == 2
    assert len(student.get("/jobs", params={"scope": "remote"}).json()) >= 1


def test_a_second_run_creates_no_duplicates_and_skips_the_llm(settings, backend, student):
    calls: list = []
    extractor = mocked_ollama(calls)
    scrape(settings, backend, extractor=extractor)
    first = {j["id"]: j for j in student.get("/jobs").json()}
    llm_calls_after_first = len(calls)

    stats, push, _ = scrape(settings, backend, extractor=extractor)
    assert stats.unchanged == 2 and stats.saved == 0
    assert push.inserted == 0 and push.unchanged == 2 and push.updated == 0
    assert len(calls) == llm_calls_after_first  # already extracted by this model + prompt

    second = {j["id"]: j for j in student.get("/jobs").json()}
    assert set(second) == set(first)  # same rows, nothing new
    assert all(second[i]["last_seen_at"] > first[i]["last_seen_at"] for i in first)  # freshness bumped by re-sending


def test_changed_posting_is_updated_in_place(settings, backend, student):
    scrape(settings, backend)
    before = {j["id"]: j for j in student.get("/jobs").json()}
    changed = (FIXTURES / "shine_detail.md").read_text().replace("Job Description", "Job Description\n---\nNEW: now hiring 50 people\n", 1)
    stats, push, _ = scrape(settings, backend, firecrawl=FakeFirecrawl(changed))
    assert push.updated == 2 and push.inserted == 0
    after = {j["id"]: j for j in student.get("/jobs").json()}
    assert set(after) == set(before)
    assert all(after[i]["updated_at"] > before[i]["updated_at"] for i in before)


def test_ollama_failure_still_delivers_the_job(settings, backend, student):
    def broken(request):
        return httpx.Response(500)

    extractor = OllamaExtractor(Settings(_env_file=None), client=httpx.Client(transport=httpx.MockTransport(broken)))
    stats, push, _ = scrape(settings, backend, extractor=extractor)
    assert stats.extraction_failed == 2 and stats.failed == 0
    assert push.inserted == 2
    assert student.get("/jobs", params={"source": "shine"}).json()  # delivered, just without LLM fields


def test_wrong_ingest_token_delivers_nothing_and_does_not_crash(settings, backend, student):
    bad = Settings(_env_file=None, output_dir=settings.output_dir, ingest_token="wrong", request_delay_seconds=0)
    stats, push, storage = run_source("shine", bad, FakeFirecrawl(), FILTERS, extract=False, push=True, backend_client=backend)
    assert stats.saved == 2 and push.failed == 2 and push.inserted == 0
    assert student.get("/jobs").json() == []
    dead = [json.loads(line) for line in storage.dead_letter_path.read_text().splitlines()]
    assert {d["stage"] for d in dead} == {"ingest"} and "INGEST_TOKEN" in dead[0]["error"]


def test_self_heals_after_a_failed_push(settings, backend, student):
    """The backend was unreachable/wrong on run 1; run 2 re-sends everything even though the scraper saw it already."""
    bad = Settings(_env_file=None, output_dir=settings.output_dir, ingest_token="wrong", request_delay_seconds=0)
    run_source("shine", bad, FakeFirecrawl(), FILTERS, extract=False, push=True, backend_client=backend)
    assert student.get("/jobs").json() == []
    stats, push, _ = run_source("shine", settings, FakeFirecrawl(), FILTERS, extract=False, push=True, backend_client=backend)
    assert stats.unchanged == 2 and push.inserted == 2
    assert len(student.get("/jobs").json()) == 2


def test_turning_extraction_on_later_reaches_the_backend(settings, backend, student):
    """First scrape without the LLM, later with it: the same text, but the backend must receive the new skills and years."""
    _, first, _ = run_source("shine", settings, FakeFirecrawl(), FILTERS, extract=False, push=True, backend_client=backend)
    assert first.inserted == 2
    before = next(j for j in student.get("/jobs").json() if j["external_id"] == "19485428")
    assert before["allowed_grads"] == []

    stats, second, _ = scrape(settings, backend)  # extraction on this time
    assert stats.extracted == 2 and second.updated == 2 and second.inserted == 0
    after = next(j for j in student.get("/jobs").json() if j["external_id"] == "19485428")
    assert after["id"] == before["id"] and after["allowed_grads"] == [2026] and after["work_mode"] == "remote"


def test_a_rerun_with_nothing_changed_does_not_touch_the_rows(settings, backend, student):
    """Re-sending everything every run is what keeps last_seen_at fresh, but it must not rewrite unchanged rows."""
    scrape(settings, backend)
    before = {j["id"]: j for j in student.get("/jobs").json()}
    stats, push, _ = scrape(settings, backend)
    assert stats.unchanged == 2 and push.unchanged == 2 and push.updated == 0
    after = {j["id"]: j for j in student.get("/jobs").json()}
    assert all(after[i]["updated_at"] == before[i]["updated_at"] for i in before)  # content untouched
    assert all(after[i]["last_seen_at"] > before[i]["last_seen_at"] for i in before)  # but seen again
