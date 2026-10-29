import json

import pytest

from scraper.adapters.base import SourceAdapter
from scraper.config import Settings
from scraper.extraction import ExtractionError, OllamaExtractor, ground
from scraper.models import JobExtraction, JobRef, RawJob, SearchFilters
from scraper.pipeline import run as run_pipeline
from scraper.storage.jsonl import JsonlStorage

OLLAMA_CHAT = "http://localhost:11434/api/chat"
POSTING = (
    "Software Engineering Intern. Build backend services in Python and Go. "
    "Requires a Bachelor's degree or B.Tech in CS. 2027 graduates only. "
    "Stipend: INR 40,000 per month. Candidates must be authorized to work in the United States. "
) * 2


def _reply(**fields) -> dict:
    return {"message": {"content": json.dumps(fields)}}


def test_ground_drops_skills_not_in_text_and_dedupes():
    data = JobExtraction(skills=["Python", "python", "Rust", " Go "])
    assert ground(data, POSTING).skills == ["Python", "Go"]


def test_ground_keeps_quoted_work_authorization():
    quote = "Candidates must be authorized to work in the United States."
    data = JobExtraction(work_authorization_restricted=True, work_authorization_note=quote)
    out = ground(data, POSTING)
    assert out.work_authorization_restricted is True and out.work_authorization_note == quote


def test_ground_drops_restriction_it_cannot_quote():
    data = JobExtraction(work_authorization_restricted=True, work_authorization_note="US citizens only")
    out = ground(data, POSTING)
    assert out.work_authorization_restricted is None and out.work_authorization_note is None
    assert ground(JobExtraction(work_authorization_restricted=True), POSTING).work_authorization_restricted is None


def test_ground_degree_needs_evidence():
    assert ground(JobExtraction(degree_required="bachelors"), POSTING).degree_required == "bachelors"
    assert ground(JobExtraction(degree_required="none"), POSTING).degree_required is None
    assert ground(JobExtraction(degree_required="phd"), POSTING).degree_required is None
    assert ground(JobExtraction(degree_required="none"), "No degree required for this role").degree_required == "none"


def test_ground_graduation_years_must_appear_in_text():
    assert ground(JobExtraction(graduation_years=[2027, 2030, 1999]), POSTING).graduation_years == [2027]


def test_ground_salary_converts_units_in_code():
    text = "Salary: ₹10 lakh - ₹25 lakh per year"
    out = ground(JobExtraction(salary_min=10, salary_max=25, salary_unit="lakh", salary_currency="INR",
                               salary_period="year"), text)
    assert (out.salary_min, out.salary_max, out.salary_currency, out.salary_period) == (1_000_000, 2_500_000, "INR", "year")
    assert out.salary_unit is None
    k = ground(JobExtraction(salary_min=135, salary_unit="thousand", salary_currency="USD"), "Pay is $135K a year")
    assert k.salary_min == 135_000


def test_ground_salary_rejects_invented_figures_and_orphans():
    bad_number = ground(JobExtraction(salary_min=99999, salary_currency="USD", salary_period="year"), POSTING)
    assert bad_number.salary_min is None and bad_number.salary_currency is None
    bad_unit = ground(JobExtraction(salary_min=40, salary_unit="crore", salary_currency="INR"), "Stipend 40 per hour")
    assert bad_unit.salary_min is None and bad_unit.salary_currency is None
    orphan = ground(JobExtraction(salary_currency="INR", salary_period="month"), POSTING)
    assert orphan.salary_currency is None and orphan.salary_period is None
    swapped = ground(JobExtraction(salary_min=50000, salary_max=40000), "pay 40,000 to 50,000")
    assert (swapped.salary_min, swapped.salary_max) == (40000, 50000)


def test_salary_unit_is_not_stored():
    assert "salary_unit" not in JobExtraction(salary_unit="lakh").model_dump()


def test_wants_skips_short_text():
    ex = OllamaExtractor(Settings(extraction_min_chars=300))
    assert not ex.wants("x" * 299) and ex.wants("x" * 300)


def test_extract_sends_schema_and_grounds_result(httpx_mock):
    httpx_mock.add_response(url=OLLAMA_CHAT, json=_reply(skills=["Python", "Rust"], graduation_years=[2027]))
    result = OllamaExtractor(Settings()).extract("SWE Intern", POSTING)
    assert result.data.skills == ["Python"] and result.data.graduation_years == [2027]
    assert result.model == "qwen2.5:3b" and result.prompt_version
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["options"]["temperature"] == 0 and body["stream"] is False
    assert body["format"]["properties"]["skills"] and "SWE Intern" in body["messages"][1]["content"]


def test_extract_repairs_one_invalid_reply(httpx_mock):
    httpx_mock.add_response(url=OLLAMA_CHAT, json={"message": {"content": "not json"}})
    httpx_mock.add_response(url=OLLAMA_CHAT, json=_reply(skills=["Go"]))
    assert OllamaExtractor(Settings()).extract("t", POSTING).data.skills == ["Go"]


def test_extract_gives_up_after_two_invalid_replies(httpx_mock):
    httpx_mock.add_response(url=OLLAMA_CHAT, json={"message": {"content": '{"skills": "oops"}'}}, is_reusable=True)
    with pytest.raises(ExtractionError):
        OllamaExtractor(Settings()).extract("t", POSTING)


class _Adapter(SourceAdapter):
    name, company = "fake", "Fake Co"

    def __init__(self, text):
        self.text = text

    def discover(self, filters):
        return [JobRef(external_id="1", url="u1")]

    def extract_external_id(self, url):
        return url

    def fetch(self, ref):
        return RawJob(ref=ref, content="")

    def normalize(self, raw):
        return {"title": "Software Engineering Intern", "employment_type": "internship", "description_text": self.text}


class _FakeExtractor:
    def __init__(self, tag="m|v1", fail=False):
        self.tag, self.fail, self.calls = tag, fail, 0

    def wants(self, text):
        return len(text) >= 300

    def extract(self, title, text):
        self.calls += 1
        if self.fail:
            raise RuntimeError("ollama down")
        from datetime import UTC, datetime

        from scraper.models import ExtractionResult
        model, version = self.tag.split("|")
        return ExtractionResult(model=model, prompt_version=version, extracted_at=datetime.now(UTC),
                                data=JobExtraction(skills=["Python"]))


FILTERS = SearchFilters(queries=[], locations=[], limit=5)


def _run(tmp_path, extractor, text=POSTING):
    return run_pipeline(_Adapter(text), FILTERS, JsonlStorage(tmp_path), Settings(max_concurrency=1), extractor)


def _lines(tmp_path):
    return [json.loads(line) for line in (tmp_path / "jobs.jsonl").read_text().splitlines()]


def test_pipeline_extracts_then_skips_unchanged(tmp_path):
    ex = _FakeExtractor()
    first = _run(tmp_path, ex)
    assert (first.saved, first.extracted) == (1, 1)
    assert _lines(tmp_path)[0]["extraction"]["data"]["skills"] == ["Python"]
    second = _run(tmp_path, ex)
    assert (second.unchanged, second.extracted, ex.calls) == (1, 0, 1)
    assert len(_lines(tmp_path)) == 1


def test_pipeline_reextracts_when_model_or_prompt_changes(tmp_path):
    _run(tmp_path, _FakeExtractor("m|v1"))
    stats = _run(tmp_path, _FakeExtractor("m|v2"))
    assert (stats.saved, stats.extracted) == (1, 1)
    assert _lines(tmp_path)[-1]["extraction"]["prompt_version"] == "v2"


def test_pipeline_extraction_failure_keeps_the_job_and_retries_next_run(tmp_path):
    stats = _run(tmp_path, _FakeExtractor(fail=True))
    assert (stats.saved, stats.extraction_failed, stats.failed) == (1, 1, 0)
    assert _lines(tmp_path)[0]["extraction"] is None
    dead = [json.loads(line) for line in (tmp_path / "dead_letter.jsonl").read_text().splitlines()]
    assert dead[0]["stage"] == "extraction"
    again = _run(tmp_path, _FakeExtractor(fail=True))
    assert (again.unchanged, again.saved) == (1, 0) and len(_lines(tmp_path)) == 1  # no duplicate line
    healed = _run(tmp_path, _FakeExtractor())
    assert healed.extracted == 1 and _lines(tmp_path)[-1]["extraction"] is not None


def test_pipeline_does_not_extract_short_text_or_without_extractor(tmp_path):
    ex = _FakeExtractor()
    stats = _run(tmp_path, ex, text="short card text")
    assert (stats.saved, ex.calls) == (1, 0)
    assert _run(tmp_path / "other", None).saved == 1
