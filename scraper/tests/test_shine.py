import json
import re
from pathlib import Path

import pytest

from scraper.adapters.shine import ShineAdapter, parse_listing, search_urls
from scraper.config import Settings
from scraper.http import PoliteClient
from scraper.models import JobRef, RawJob, SearchFilters
from scraper.pipeline import build_record
from scraper.relevance import assess

FIXTURES = Path(__file__).parent.parent / "fixtures"
DETAIL_URL = "https://www.shine.com/jobs/associate-software-developer-fresher-wfh-pune/recruit-crm/19485428"


def _read(name):
    return (FIXTURES / name).read_text()


def _firecrawl(markdown):
    return json.dumps({"success": True, "data": {"markdown": markdown}})


@pytest.fixture
def adapter():
    return ShineAdapter(client=None, settings=Settings())


@pytest.fixture
def client(httpx_mock):
    httpx_mock.add_response(url="https://www.shine.com/robots.txt", text="User-agent: *\nDisallow: /jobs/jobs/\nAllow: /\n",
                            is_reusable=True)
    c = PoliteClient("test", delay_seconds=0)
    yield c
    c.close()


def test_search_urls():
    assert search_urls("software developer fresher", "India", 1) == "https://www.shine.com/job-search/software-developer-fresher-jobs"
    assert search_urls("Java Developer", "Bengaluru", 1) == "https://www.shine.com/job-search/java-developer-jobs-in-bangalore"
    assert search_urls("java developer", "India", 3).endswith("java-developer-jobs-3")


def test_extract_external_id(adapter):
    assert adapter.extract_external_id(DETAIL_URL) == "19485428"
    with pytest.raises(ValueError):
        adapter.extract_external_id("https://www.shine.com/job-search/java-jobs")


def test_parse_listing_cards():
    cards = parse_listing(_read("shine_listing.md"))
    assert len(cards) >= 10
    first = cards[0]
    assert first["title"] == "Associate Software Developer Fresher (WFH) (Pune)"
    assert first["company"] == "Recruit CRM"
    assert first["min_years"] == 0
    assert first["skills"][:2] == ["Java", "Python"]
    assert "?" not in first["url"] and first["url"].endswith("/19485428")


def test_discover_keeps_fresher_roles_and_stops_when_pages_repeat(httpx_mock, client):
    listing = _read("shine_listing.md")
    httpx_mock.add_response(url=re.compile(r".*/v2/scrape$"), method="POST", text=_firecrawl(listing), is_reusable=True)
    refs = ShineAdapter(client, Settings()).discover(
        SearchFilters(queries=["software developer fresher"], locations=["India"], limit=50))
    ids = [r.external_id for r in refs]
    assert refs and len(ids) == len(set(ids))  # page 2 repeated page 1, so discovery stopped, no duplicates
    assert all(r.hints["min_years"] in (0, 1, None) for r in refs)


def test_normalize_detail_page_end_to_end(adapter):
    ref = JobRef(external_id="19485428", url=DETAIL_URL, hints={
        "title": "Associate Software Developer Fresher (WFH) (Pune)", "company": "Recruit CRM", "min_years": 0, "skills": []})
    out = adapter.normalize(RawJob(ref=ref, content=_read("shine_detail.md")))
    assert out["company"] == "Recruit CRM"
    assert out["locations"] == ["Pune"]
    assert out["employment_type"].value == "full_time"
    assert out["work_mode"].value == "remote"
    assert out["min_experience_years"] == 0
    assert out["required_qualifications"] == ["Java", "Python", "ML", "AI"]
    assert out["description_text"].startswith("About the job:")
    assert "Recruit CRM, a global" in out["description_text"]
    assert "Similar" not in out["description_text"] and "jobs nearby" not in out["description_text"]
    # and the shared filter accepts it
    from datetime import UTC, datetime
    record = build_record(adapter, RawJob(ref=ref, content=_read("shine_detail.md")), datetime.now(UTC))
    assert record.source == "shine" and assess(record).ok


def test_discover_gives_each_query_a_fair_share(httpx_mock, client):
    """With a small limit the first query must not use it all: later queries (ML, cyber) still get postings."""
    pages = {}
    for slug, first_id in (("software", 1000), ("machine-learning", 2000), ("cyber", 3000)):
        cards = "\n".join(
            f"Co{n} 1 day ago\n\n### [{slug.title()} Fresher Engineer {'ABCDEFGHIJ'[n]}](https://www.shine.com/jobs/{slug}-{n}/co/{first_id + n}?jobtype=cr)\n\n"
            f"0 to 2 YrsNot DisclosedPune\n\nRequired:Python" for n in range(10))
        pages[slug] = cards
    def respond(request):
        body = json.loads(request.content)["url"]
        key = "software" if "software" in body else "machine-learning" if "machine-learning" in body else "cyber"
        import httpx
        return httpx.Response(200, text=_firecrawl(pages[key]))
    httpx_mock.add_callback(respond, url=re.compile(r".*/v2/scrape$"), is_reusable=True)
    refs = ShineAdapter(client, Settings()).discover(SearchFilters(
        queries=["software developer fresher", "machine-learning fresher", "cyber fresher"], locations=["India"], limit=9))
    titles = [r.hints["title"] for r in refs]
    assert len(refs) == 9
    assert sum("Software" in t for t in titles) == 3 and sum("Machine-Learning" in t for t in titles) == 3 and sum("Cyber" in t for t in titles) == 3
