import pytest

from scraper.adapters.microsoft import MicrosoftAdapter, html_to_lines, parse_sections
from scraper.config import Settings
from scraper.models import EmploymentType, JobRef, RawJob, WorkMode


@pytest.fixture
def adapter():
    return MicrosoftAdapter(client=None, settings=Settings())


def test_extract_external_id(adapter):
    url = "https://apply.careers.microsoft.com/careers/job/1970393556911730?domain=microsoft.com"
    assert adapter.extract_external_id(url) == "1970393556911730"
    with pytest.raises(ValueError):
        adapter.extract_external_id("https://example.com/jobs/1")


def test_html_to_lines_renders_bullets():
    lines = html_to_lines("<b>Responsibilities</b><br><ul><li>One</li><li>Two</li></ul>")
    assert lines == ["Responsibilities", "- One", "- Two"]


def test_parse_sections_bullets_and_paragraph_fallback():
    lines = [
        "Overview", "Hello world.",
        "Responsibilities", "- Build", "- Test",
        "Qualifications", "Required Qualifications:", "- Degree",
        "Preferred Qualifications:", "Knows DSA",
        "Microsoft is an equal opportunity employer.",
    ]
    out = parse_sections(lines)
    assert out["overview"] == "Hello world."
    assert out["responsibilities"] == ["Build", "Test"]
    assert out["required_qualifications"] == ["Degree"]
    assert out["preferred_qualifications"] == ["Knows DSA"]  # paragraph fallback


def test_normalize_real_detail_fixture(adapter, detail_data):
    ref = JobRef(external_id="1970393556911730", url="u")
    raw = RawJob(ref=ref, content="\n".join(html_to_lines(detail_data["jobDescription"])), fields=detail_data)
    out = adapter.normalize(raw)
    assert out["title"] == "Software Engineering INTERN"
    assert out["requisition_id"] == "200041085"
    assert out["employment_type"] == EmploymentType.internship
    assert out["work_mode"] == WorkMode.onsite
    assert str(out["posted_date"]) == "2026-09-18"
    assert len(out["responsibilities"]) == 6
    assert any("Computer Science" in q for q in out["required_qualifications"])
    assert "themeOptions" not in out["description_text"]


def test_employment_type_falls_back_to_title(adapter):
    raw = RawJob(ref=JobRef(external_id="1", url="u"), content="", fields={"name": "Research INTERN"})
    assert adapter.normalize(raw)["employment_type"] == EmploymentType.internship
    raw = RawJob(ref=JobRef(external_id="1", url="u"), content="", fields={"name": "Engineer"})
    assert adapter.normalize(raw)["employment_type"] == EmploymentType.unknown
