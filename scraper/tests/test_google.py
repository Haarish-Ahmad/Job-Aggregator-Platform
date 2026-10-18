from pathlib import Path

import pytest

from scraper.adapters.google import (
    GoogleAdapter,
    _canonical_urls,
    _parse_ds1,
    _posted_date,
    _split_qualifications,
)
from scraper.config import Settings
from scraper.models import JobRef, RawJob

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def adapter():
    return GoogleAdapter(client=None, settings=Settings())


@pytest.fixture
def listing_html():
    return (FIXTURES / "google_listing.html").read_text(errors="ignore")


def test_extract_external_id(adapter):
    url = "https://www.google.com/about/careers/applications/jobs/results/141419870129398470-policy-specialist"
    assert adapter.extract_external_id(url) == "141419870129398470"
    with pytest.raises(ValueError):
        adapter.extract_external_id("https://example.com/jobs/1")


def test_parse_ds1_finds_real_jobs(listing_html):
    jobs = _parse_ds1(listing_html)
    assert jobs
    assert len(jobs) >= 1
    assert any("Policy Specialist" in job[1] for job in jobs)


def test_canonical_urls_map_id_to_real_slug(listing_html):
    urls = _canonical_urls(listing_html)
    assert urls
    # one of the jobs we saw in investigation
    assert any("policy-specialist" in url for url in urls.values())


def test_split_qualifications_separates_minimum_and_preferred():
    html = (
        "<h3>Minimum qualifications:</h3><ul><li>Bachelor's degree.</li>"
        "<li>5 years experience.</li></ul>"
        "<h3>Preferred qualifications:</h3><ul><li>Knows Python.</li></ul>"
    )
    required, preferred = _split_qualifications(html)
    assert required == ["Bachelor's degree.", "5 years experience."]
    assert preferred == ["Knows Python."]


def test_split_qualifications_handles_empty_html():
    assert _split_qualifications("") == ([], [])


def test_posted_date_from_timestamp_pair():
    assert _posted_date([None] * 12 + [[1790773648, 398000000]]) is not None
    assert _posted_date([None] * 12 + [None]) is None
    assert _posted_date([None] * 5) is None  # too short


def test_normalize_real_fixture_job(adapter, listing_html):
    jobs = _parse_ds1(listing_html)
    job = next(j for j in jobs if "Policy Specialist" in j[1])
    raw = RawJob(ref=JobRef(external_id=str(job[0]), url="u"), content="", fields={"job": job})
    out = adapter.normalize(raw)
    assert out["title"] == "Policy Specialist"
    assert out["locations"]
    assert any("Hyderabad" in loc for loc in out["locations"])
    assert out["required_qualifications"]
    assert out["preferred_qualifications"]
    assert "themeOptions" not in out["description_text"]


def test_normalize_detects_internship_from_title(adapter):
    job = [1, "Software Engineering Intern, Summer 2027"] + [None] * 19
    raw = RawJob(ref=JobRef(external_id="1", url="u"), content="", fields={"job": job})
    out = adapter.normalize(raw)
    assert out["employment_type"] == "internship"

    job2 = [2, "Policy Specialist"] + [None] * 19
    raw2 = RawJob(ref=JobRef(external_id="2", url="u"), content="", fields={"job": job2})
    assert adapter.normalize(raw2)["employment_type"] == "unknown"
