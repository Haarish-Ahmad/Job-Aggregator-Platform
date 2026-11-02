import re
from pathlib import Path

import pytest

from scraper.adapters.ycombinator import YCombinatorAdapter, _page_props, _years_from_label
from scraper.location import in_india as _in_india
from scraper.config import Settings
from scraper.http import PoliteClient
from scraper.models import JobRef, RawJob, SearchFilters
from scraper.pipeline import build_record
from scraper.relevance import assess

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _read(name):
    return (FIXTURES / name).read_text(errors="ignore")


@pytest.fixture
def adapter():
    return YCombinatorAdapter(client=None, settings=Settings())


@pytest.fixture
def client(httpx_mock):
    httpx_mock.add_response(url="https://www.ycombinator.com/robots.txt",
                            text="User-agent: *\nDisallow: /verify/*\nAllow: /\n", is_reusable=True)
    c = PoliteClient("test", delay_seconds=0)
    yield c
    c.close()


def test_extract_external_id(adapter):
    url = "https://www.ycombinator.com/companies/candid-health/jobs/WIMeHdk-software-engineer"
    assert adapter.extract_external_id(url) == "WIMeHdk"
    with pytest.raises(ValueError):
        adapter.extract_external_id("https://example.com/jobs/1")


def test_years_from_label():
    assert _years_from_label("3+ years") == 3
    assert _years_from_label("Any (new grads ok)") == 0
    assert _years_from_label(None) is None


def test_page_props_reads_embedded_json():
    postings = _page_props(_read("yc_jobs_swe.html"))["jobPostings"]
    assert len(postings) > 10 and "title" in postings[0]


def test_discover_keeps_only_software_roles_an_undergrad_can_take(httpx_mock, client):
    httpx_mock.add_response(url=re.compile(r".*/jobs/role/software-engineer$"), text=_read("yc_jobs_swe.html"))
    refs = YCombinatorAdapter(client, Settings()).discover(SearchFilters(queries=[], locations=[""], limit=50))
    titles = [r.hints["job"]["title"] for r in refs]
    assert "Software Engineering Intern" in titles
    assert not any(re.search(r"Staff|Senior|Principal|Marketing", t) for t in titles)
    assert all(r.hints["job"]["role"] == "eng" for r in refs)
    assert all((r.hints["job"]["minExperience"] or "").startswith(("Any", "0", "1")) or r.hints["job"]["type"] == "Internship" or r.hints["job"]["minExperience"] is None for r in refs)


def test_in_india():
    assert _in_india("Bengaluru, KA, IN / Bengaluru, Karnataka, IN")
    assert _in_india("India / Remote (US)")
    assert _in_india("SG / HK / IN / US / Remote (SG; HK; IN; US)")
    assert _in_india("South East Asia & India")
    assert not _in_india("Indianapolis, IN, US")
    assert not _in_india("Remote (US)")
    assert not _in_india("San Francisco, CA, US / Remote (US; CA)")


def test_discover_india_only_uses_both_pages_and_survives_missing_page(httpx_mock, client):
    httpx_mock.add_response(url=re.compile(r".*/software-engineer$"), text=_read("yc_jobs_swe.html"))
    httpx_mock.add_response(url=re.compile(r".*/software-engineer/india$"), text=_read("yc_jobs_india.html"))
    httpx_mock.add_response(url=re.compile(r".*/software-engineer/atlantis$"), status_code=404)
    refs = YCombinatorAdapter(client, Settings()).discover(
        SearchFilters(queries=[], locations=["India", "Atlantis"], limit=50))
    assert refs
    assert all(_in_india(r.hints["job"]["location"]) for r in refs)
    titles = [r.hints["job"]["title"] for r in refs]
    assert any("Fullstack" in t for t in titles)  # Bengaluru role that only the global page lists
    assert not any("Videographer" in t for t in titles)


def test_normalize_detail_page_end_to_end(adapter):
    detail = _page_props(_read("yc_job_detail.html"))["job"]
    ref = JobRef(external_id="59310", url="https://www.ycombinator.com/x", hints={"job": detail})
    raw = RawJob(ref=ref, content=detail["description"], fields={"job": detail})
    out = adapter.normalize(raw)
    assert out["company"] == "Candid Health"
    assert out["title"] == "Software Engineer"
    assert out["employment_type"].value == "full_time"
    assert out["min_experience_years"] == 3
    assert "San Francisco, CA, US" in out["locations"]
    assert out["description_text"].startswith("## What we do")

    record = build_record(adapter, raw, __import__("datetime").datetime.now())
    assert record.company == "Candid Health"
    assert assess(record).reason == "requires 3+ years"


def test_internship_posting_passes_filter(adapter):
    job = {"title": "Software Engineering Intern", "type": "Internship", "companyName": "Aviator",
           "location": "San Francisco", "prettyRole": "Engineering", "minExperience": None, "skills": []}
    raw = RawJob(ref=JobRef(external_id="1", url="u", hints={"job": job}), content="desc", fields={"job": job})
    record = build_record(adapter, raw, __import__("datetime").datetime.now())
    assert record.employment_type.value == "internship"
    assert assess(record).ok
