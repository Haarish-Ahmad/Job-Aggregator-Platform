import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from scraper.adapters.greenhouse import GreenhouseAdapter, _split_sections
from scraper.config import Settings
from scraper.http import PoliteClient
from scraper.models import SearchFilters
from scraper.pipeline import build_record
from scraper.relevance import assess

FIXTURES = Path(__file__).parent.parent / "fixtures"
BOARDS = json.loads((FIXTURES / "greenhouse_boards_sample.json").read_text())


@pytest.fixture
def client(httpx_mock):
    httpx_mock.add_response(url="https://boards-api.greenhouse.io/robots.txt",
                            text="User-agent: *\nDisallow: /embed/\n", is_reusable=True)
    c = PoliteClient("test", delay_seconds=0)
    yield c
    c.close()


def _adapter(client, companies):
    return GreenhouseAdapter(client, Settings(greenhouse_companies=companies))


def _mock_boards(httpx_mock, tokens):
    for token in tokens:
        httpx_mock.add_response(url=re.compile(rf".*/boards/{token}/jobs\?content=true"), json=BOARDS[token])


def test_extract_external_id():
    adapter = GreenhouseAdapter(client=None, settings=Settings())
    assert adapter.extract_external_id("https://stripe.com/jobs/search?gh_jid=8031833") == "8031833"
    assert adapter.extract_external_id("https://boards.greenhouse.io/x/jobs/123") == "123"
    with pytest.raises(ValueError):
        adapter.extract_external_id("https://example.com/job/1")


def test_discover_filters_location_and_title_across_companies(httpx_mock, client):
    _mock_boards(httpx_mock, ["rubrik", "stripe", "coinbase"])
    refs = _adapter(client, "rubrik,stripe,coinbase").discover(
        SearchFilters(queries=[], locations=["India"], limit=50))
    titles = [r.hints["job"]["title"] for r in refs]
    assert any("Winter Intern" in t for t in titles) and "Software Engineer, Intern" in titles
    assert all("Marketing" not in t for t in titles)  # coinbase postings are not in India anyway


def test_discover_without_location_keeps_other_countries_but_drops_marketing(httpx_mock, client):
    _mock_boards(httpx_mock, ["coinbase"])
    refs = _adapter(client, "coinbase").discover(SearchFilters(queries=[], locations=[""], limit=50))
    titles = [r.hints["job"]["title"] for r in refs]
    assert titles and not any("Marketing" in t for t in titles)


def test_discover_round_robins_companies_under_a_small_limit(httpx_mock, client):
    _mock_boards(httpx_mock, ["rubrik", "stripe"])
    refs = _adapter(client, "rubrik,stripe").discover(SearchFilters(queries=[], locations=["India"], limit=2))
    assert {r.hints["job"]["company_name"] for r in refs} == {"Rubrik Job Board", "Stripe"}


def test_discover_survives_a_missing_board(httpx_mock, client):
    httpx_mock.add_response(url=re.compile(r".*/boards/nosuchco/jobs.*"), status_code=404)
    _mock_boards(httpx_mock, ["stripe"])
    refs = _adapter(client, "nosuchco,stripe").discover(SearchFilters(queries=[], locations=["India"], limit=10))
    assert refs


def test_normalize_real_intern_posting_passes_filter(httpx_mock, client):
    _mock_boards(httpx_mock, ["stripe"])
    adapter = _adapter(client, "stripe")
    ref = adapter.discover(SearchFilters(queries=[], locations=["India"], limit=5))[0]
    raw = adapter.fetch(ref)
    record = build_record(adapter, raw, datetime.now())
    assert record.company == "Stripe"
    assert record.employment_type.value == "internship"
    assert record.locations == ["Bengaluru"]
    assert record.posted_date is not None
    assert record.description_text and "&lt;" not in record.description_text
    assert assess(record).ok


def test_senior_india_posting_is_rejected_by_filter():
    adapter = GreenhouseAdapter(client=None, settings=Settings())
    from scraper.models import JobRef, RawJob
    job = BOARDS["okta"]["jobs"][0]
    raw = RawJob(ref=JobRef(external_id=str(job["id"]), url=job["absolute_url"]), content="", fields={"job": job})
    record = build_record(adapter, raw, datetime.now())
    assert not assess(record).ok


def test_split_sections():
    lines = ["What you'll do", "- build things", "Qualifications", "- 2 years of Python", "- BS in CS",
             "Nice to have", "- Rust", "About us", "- we are great"]
    out = _split_sections(lines)
    assert out["responsibilities"] == ["build things"]
    assert out["required"] == ["2 years of Python", "BS in CS"]
    assert out["preferred"] == ["Rust"]
