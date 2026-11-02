from datetime import UTC, datetime

import pytest

from scraper.models import EmploymentType, JobRecord
from scraper.relevance import assess, min_years_from_items, min_years_from_text, title_excluded, too_experienced


def _record(title, employment_type=EmploymentType.unknown, years=None, department=None, quals=()):
    return JobRecord(
        source="s", company="c", external_id="1", url="u", scraped_at=datetime.now(UTC),
        content_hash="h", title=title, employment_type=employment_type,
        min_experience_years=years, department=department, required_qualifications=list(quals),
    )


@pytest.mark.parametrize("title,reason", [
    ("Marketing Design Lead", "non-software role"),
    ("Product Management INTERN", "non-software role"),
    ("UI/UX Designer Intern", "non-software role"),
    ("Silicon Engineering Intern", "non-software role"),
    ("Staff Software Engineer", "senior role"),
    ("Software Engineer II", "senior role"),
    ("SDE 2", "senior role"),
    ("Engineering Manager", "senior role"),
    ("Software Engineering PhD Intern", "graduate-degree role"),
    ("Senio Applied Scientist - Ads", "senior role"),
    ("Snr Data & Applied Scientist", "senior role"),
    ("DevOps Cloud Engineering Consultant - TS/SCI", "non-software role"),
    ("Partner Technology Strategist", "non-software role"),
    ("Design Verification Engineer - DDR Memory", "non-software role"),
    ("Physical Security Engineer", "non-software role"),
    ("Software Engineer - Reliability (US Citizen)", "work-authorization restricted"),
    ("Backend Engineer (Security Clearance)", "work-authorization restricted"),
])
def test_title_excluded(title, reason):
    assert title_excluded(title) == reason


@pytest.mark.parametrize("title", [
    "Software Engineering Intern", "Software Design Engineer", "Data Science INTERN",
    "Backend Developer Intern", "Software Engineer, Early Career",
])
def test_title_not_excluded(title):
    assert title_excluded(title) is None


def test_min_years_from_text():
    assert min_years_from_text("5+ years of experience") == 5
    assert min_years_from_text("1-3 years in Python") == 1
    assert min_years_from_text("5 years, or 3 years with a Master's") == 3
    assert min_years_from_text("Bachelor's degree or equivalent") is None


def test_too_experienced_ignores_new_grad_flag_only_when_title_is_entry():
    assert too_experienced("Software Engineer", False, 3)
    assert not too_experienced("Software Engineer", False, 1)
    assert not too_experienced("Software Engineering Intern", False, 3)
    assert not too_experienced("Software Engineer", True, 3)


def test_assess_accepts_internships_and_entry_level():
    assert assess(_record("Software Engineering Intern", EmploymentType.internship)).ok
    assert assess(_record("Software Engineer", years=0)).ok
    assert assess(_record("New Grad Software Engineer")).ok
    assert assess(_record("Software Engineer (New Grad)", EmploymentType.full_time)).ok
    assert assess(_record("Early Career Backend Developer", EmploymentType.full_time, years=0)).ok
    assert assess(_record("Graduate Program Software Engineer", EmploymentType.full_time, years=1)).ok


def test_assess_rejects_experienced_unknown_and_non_software():
    assert assess(_record("Software Engineer", years=5)).reason == "requires 5+ years"
    assert assess(_record("Software Engineer", EmploymentType.full_time)).reason == "no entry-level signal"
    assert assess(_record("Operations Intern", EmploymentType.internship)).reason == "not a software role"


def test_assess_vague_title_needs_software_text():
    vague = _record("Research Intern", EmploymentType.internship)
    assert assess(vague).reason == "not a software role"
    coder = _record("Research Intern", EmploymentType.internship, quals=["Strong Python and algorithms"])
    assert assess(coder).ok


def test_software_trusted_skips_software_check_but_not_exclusions():
    web = _record("Web Development", EmploymentType.internship)
    assert assess(web, software_trusted=True).ok
    assert not assess(_record("Digital Marketing", EmploymentType.internship), software_trusted=True).ok


def test_min_years_from_items_uses_only_the_bachelors_path():
    items = [
        "Bachelor's Degree in CS AND 4+ years related experience",
        "OR Master's Degree in CS AND 3+ years related experience",
        "OR Doctorate in CS AND 1+ year(s) related experience",
    ]
    assert min_years_from_items(items) == 4
    assert min_years_from_items(["Master's Degree AND 1+ year of experience"]) is None
    assert min_years_from_items(["Strong Python", "2+ years of Java"]) == 2


def test_non_software_department_is_rejected():
    rec = _record("Associate Solutions Engineer", EmploymentType.full_time, years=0, department="Sales Engineering")
    assert assess(rec).reason == "non-software department"


def test_advanced_degree_alternative_is_ignored():
    from scraper.relevance import min_years_from_items

    items = ["2 years of experience with software development, or 1 year of experience with an advanced degree."]
    assert min_years_from_items(items) == 2


def test_technical_support_is_not_software():
    from scraper.relevance import title_excluded

    assert title_excluded("Technical Support Engineering") == "non-software role"


@pytest.mark.parametrize("title", [
    "Machine Learning Engineer Fresher", "AI Engineer Intern", "Data Scientist Trainee", "NLP Engineer",
    "Cyber Security Analyst Fresher", "SOC Analyst", "Penetration Tester Intern", "Information Security Engineer",
    "Data Engineer Fresher", "Generative AI Developer", "Computer Vision Intern", "MLOps Engineer",
])
def test_assess_accepts_ml_ai_data_and_cyber_fresher_roles(title):
    assert assess(_record(title, EmploymentType.full_time, years=0)).ok, title


@pytest.mark.parametrize("title", ["Business Analyst", "Security Guard", "Physical Security Officer", "Security Sales Executive"])
def test_assess_still_rejects_look_alike_non_tech_roles(title):
    assert not assess(_record(title, EmploymentType.full_time, years=0)).ok, title
