import pytest

from scraper.adapters.amazon import AmazonAdapter
from scraper.adapters import REGISTRY
from scraper.config import Settings
from scraper.models import EmploymentType, JobRef, RawJob, SearchFilters


@pytest.fixture
def adapter():
    return AmazonAdapter(client=None, settings=Settings(_env_file=None))


def test_amazon_adapter_is_registered():
    assert REGISTRY["amazon"] is AmazonAdapter


def _job(job_id: str, title: str = "Software Engineer") -> dict:
    return {
        "job_path": f"/en/jobs/{job_id}/software-engineer",
        "title": title,
        "location": "Bengaluru, Karnataka, India",
    }


def test_extract_external_id(adapter):
    assert adapter.extract_external_id("https://www.amazon.jobs/en/jobs/10386857/software-engineer") == "10386857"
    with pytest.raises(ValueError):
        adapter.extract_external_id("https://example.com/jobs/1")


def test_discover_paginates_and_deduplicates_results(adapter):
    class FakeClient:
        def __init__(self):
            self.calls = []

        def get_json(self, url, *, params, headers):
            self.calls.append(params)
            assert headers == {"Accept-Encoding": "gzip, deflate"}
            foreign_job = _job("2")
            foreign_job["location"] = "New York, NY, US"
            if params["offset"] == 0:
                jobs = [_job("1"), foreign_job]
            elif params["offset"] == 2:
                jobs = [foreign_job, _job("3")]
            else:
                jobs = [_job("4")]
            return {"hits": 5, "jobs": jobs}

    client = FakeClient()
    adapter.client = client
    refs = adapter.discover(SearchFilters(queries=["engineer"], locations=["India"], limit=3))

    assert [ref.external_id for ref in refs] == ["1", "3", "4"]
    assert [call["offset"] for call in client.calls] == [0, 2, 4]
    assert [call["result_limit"] for call in client.calls] == [100, 100, 100]


def test_normalize_search_result(adapter):
    job = {
        "id_icims": "REQ-42",
        "title": "Software Development Engineer Intern",
        "is_intern": True,
        "job_schedule_type": "Full-time",
        "job_category": "Software Development",
        "posted_date": "April  9, 2026",
        "description_short": "<p>Build reliable services.</p>",
        "description": "<p>Design scalable web APIs.</p>",
        "basic_qualifications": "<ul><li>Computer Science degree</li></ul>",
        "preferred_qualifications": "<ul><li>Python experience</li></ul>",
        "locations": [
            '{"normalizedLocation":"Bengaluru, Karnataka, IND","city":"Bengaluru",'
            '"normalizedStateName":"Karnataka","normalizedCountryCode":"IND",'
            '"normalizedCountryName":"India"}'
        ],
    }
    ref = JobRef(external_id="10386857", url="https://www.amazon.jobs/en/jobs/10386857/software-engineer")
    raw = RawJob(ref=ref, content="", fields={"job": job})

    normalized = adapter.normalize(raw)

    assert normalized["title"] == job["title"]
    assert normalized["requisition_id"] == "REQ-42"
    assert normalized["employment_type"] == EmploymentType.internship
    assert normalized["locations"] == ["Bengaluru, Karnataka, India"]
    assert str(normalized["posted_date"]) == "2026-04-09"
    assert normalized["required_qualifications"] == ["Computer Science degree"]
    assert normalized["preferred_qualifications"] == ["Python experience"]
    assert normalized["overview"] == "Build reliable services."
    assert "Design scalable web APIs." in normalized["description_text"]


def test_normalize_handles_missing_optional_fields(adapter):
    raw = RawJob(
        ref=JobRef(external_id="1", url="https://www.amazon.jobs/en/jobs/1/engineer"),
        content="",
        fields={"job": {"title": "Engineer", "posted_date": "not a date"}},
    )

    normalized = adapter.normalize(raw)

    assert adapter.company == "Amazon"
    assert normalized["posted_date"] is None
    assert normalized["locations"] == []
    assert normalized["employment_type"] == EmploymentType.unknown
