import copy
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from scraper.adapters.unstop import UnstopAdapter
from scraper.config import Settings
from scraper.http import PoliteClient
from scraper.models import JobRef, RawJob, SearchFilters
from scraper.pipeline import build_record
from scraper.relevance import assess

SAMPLE = json.loads((Path(__file__).parent.parent / "fixtures" / "unstop_sample.json").read_text())
# The robots.txt rules that matter: the longer Allow must beat the broader Disallow.
ROBOTS = "User-agent: *\nAllow: /api/public/*\nDisallow: /api/*\n"


def _page(*jobs, last_page=1):
    return {"data": {"data": list(jobs), "last_page": last_page, "total": len(jobs)}}


@pytest.fixture
def client(httpx_mock):
    httpx_mock.add_response(url="https://unstop.com/robots.txt", text=ROBOTS, is_reusable=True)
    c = PoliteClient("test", delay_seconds=0)
    yield c
    c.close()


def _discover(client, queries=("software",), locations=("India",), limit=50):
    return UnstopAdapter(client, Settings()).discover(
        SearchFilters(queries=list(queries), locations=list(locations), limit=limit)
    )


def _raw(job):
    return RawJob(ref=JobRef(external_id=str(job["id"]), url="u", hints={"job": job}), content="", fields={"job": job})


def _record(job):
    return build_record(UnstopAdapter(None, Settings()), _raw(job), datetime.now())


def test_extract_external_id():
    adapter = UnstopAdapter(None, Settings())
    assert adapter.extract_external_id("https://unstop.com/jobs/associate-software-engineer-goldman-sachs-1765706") == "1765706"
    with pytest.raises(ValueError):
        adapter.extract_external_id("https://unstop.com/about")


def test_discover_keeps_only_software_roles_open_to_students(httpx_mock, client):
    jobs = [SAMPLE[k] for k in ("goldman", "fresher_job", "wfh_job", "experienced_only", "network_function")]
    httpx_mock.add_response(url=re.compile(r".*opportunity=jobs.*"), json=_page(*jobs))
    httpx_mock.add_response(url=re.compile(r".*opportunity=internships.*"), json=_page(SAMPLE["internship"]))
    titles = {r.hints["job"]["title"].strip() for r in _discover(client)}
    assert titles == {"Associate Software Engineer", "Software Developer", "Graduate Software Engineer",
                      "Frontend Developer Internship"}  # not: Senior (experienced-only), Network (wrong function)


def test_discover_follows_pages_dedupes_and_respects_limit(httpx_mock, client):
    httpx_mock.add_response(url=re.compile(r".*opportunity=jobs.*page=1&.*"), json=_page(SAMPLE["goldman"], last_page=2))
    httpx_mock.add_response(url=re.compile(r".*opportunity=jobs.*page=2&.*"), json=_page(SAMPLE["goldman"], SAMPLE["fresher_job"]))
    httpx_mock.add_response(url=re.compile(r".*opportunity=internships.*"), json=_page())
    refs = _discover(client)
    assert [r.external_id for r in refs] == [str(SAMPLE["goldman"]["id"]), str(SAMPLE["fresher_job"]["id"])]
    httpx_mock.add_response(url=re.compile(r".*opportunity=jobs.*page=1&.*"), json=_page(SAMPLE["goldman"], SAMPLE["fresher_job"]))
    assert len(_discover(client, limit=1)) == 1


def test_discover_drops_non_india_places_but_keeps_remote(httpx_mock, client):
    abroad = copy.deepcopy(SAMPLE["fresher_job"])
    abroad["id"] = 1
    abroad["locations"] = [{"city": "Dublin", "state": "Leinster", "country": "Ireland"}]
    httpx_mock.add_response(url=re.compile(r".*opportunity=jobs.*"), json=_page(abroad, SAMPLE["wfh_job"]))
    httpx_mock.add_response(url=re.compile(r".*opportunity=internships.*"), json=_page())
    assert [r.external_id for r in _discover(client)] == [str(SAMPLE["wfh_job"]["id"])]
    httpx_mock.add_response(url=re.compile(r".*opportunity=jobs.*"), json=_page(abroad))
    httpx_mock.add_response(url=re.compile(r".*opportunity=internships.*"), json=_page())
    assert len(_discover(client, locations=("",))) == 1  # no location wanted -> keep everything


def test_search_term_is_sent(httpx_mock, client):
    httpx_mock.add_response(url=re.compile(r".*/api/public/.*"), json=_page(), is_reusable=True)
    _discover(client, queries=("machine learning",))
    assert all("searchTerm=machine+learning" in str(r.url) or "searchTerm=machine%20learning" in str(r.url)
               for r in httpx_mock.get_requests() if "/api/" in str(r.url))


def test_normalize_job_with_salary_and_eligibility():
    out = UnstopAdapter(None, Settings()).normalize(_raw(SAMPLE["goldman"]))
    assert out["company"] == "Goldman Sachs" and out["title"] == "Associate Software Engineer"
    assert out["employment_type"].value == "full_time" and out["work_mode"].value == "onsite"
    assert out["locations"] == ["Bangalore, Karnataka, India"]
    assert out["min_experience_years"] == 0  # open to Freshers
    assert "Eligibility: Experienced Professionals, Fresher" in out["description_text"]
    assert "Python" in out["required_qualifications"] and out["department"] == "DevOps, Software Development"
    assert out["posted_date"] is not None and "<" not in out["description_text"]


def test_normalize_remote_job_and_internship():
    wfh = UnstopAdapter(None, Settings()).normalize(_raw(SAMPLE["wfh_job"]))
    assert wfh["work_mode"].value == "remote" and wfh["locations"] == ["Work from home"]
    internship = UnstopAdapter(None, Settings()).normalize(_raw(SAMPLE["internship"]))
    assert internship["employment_type"].value == "internship"


def test_job_titled_internship_is_labelled_internship():
    out = UnstopAdapter(None, Settings()).normalize(_raw(SAMPLE["internship_titled_job"]))
    assert out["employment_type"].value == "internship"


def test_salary_text_formats_currency_and_period():
    job = copy.deepcopy(SAMPLE["fresher_job"])
    job["jobDetail"].update(min_salary=300000, max_salary=500000, currency="fa-rupee", pay_in="annually", show_salary=1)
    assert "Salary: ₹300,000-₹500,000 annually" in UnstopAdapter(None, Settings()).normalize(_raw(job))["description_text"]
    job["jobDetail"]["show_salary"] = 0
    assert "Salary" not in UnstopAdapter(None, Settings()).normalize(_raw(job))["description_text"]


def test_good_postings_pass_the_shared_filter():
    for key in ("goldman", "fresher_job", "wfh_job", "internship"):
        assert assess(_record(SAMPLE[key])).ok, key


def test_robots_longest_match_allows_the_public_api(httpx_mock, client):
    httpx_mock.add_response(url=re.compile(r".*/api/public/.*"), json=_page())
    client.get_json("https://unstop.com/api/public/opportunity/search-result", params={"opportunity": "jobs"})
    with pytest.raises(Exception, match="robots"):
        client.get_json("https://unstop.com/api/other")
