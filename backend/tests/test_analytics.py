"""Analytics endpoints (SQL aggregations) and curriculum alignment."""
import pytest

from config import get_settings
from conftest import INGEST_HEADERS, register

pytestmark = pytest.mark.usefixtures("db_clean")


def seed(client):
    rows = [
        ("Acme", "Dev 1", ["python", "sql"], "internship", "shine", True, False),
        ("Acme", "Dev 2", ["python", "docker"], "full_time", "shine", True, False),
        ("Globex", "Dev 3", ["python", "react"], "full_time", "unstop", False, True),
        ("Globex", "Dev 4", ["java"], "internship", "unstop", True, False),
        ("Initech", "Dev 5", [], "full_time", "google", False, False),
    ]
    jobs = [{"company_name": c, "title": t, "apply_url": f"https://x.com/{i}", "source": s, "external_id": str(i),
             "required_skills": sk, "job_type": jt, "is_india": ind, "is_remote": rem}
            for i, (c, t, sk, jt, s, ind, rem) in enumerate(rows)]
    assert client.post("/internal/jobs", json={"jobs": jobs}, headers=INGEST_HEADERS).json()["inserted"] == 5


@pytest.fixture
def data(admin):
    seed(admin)
    return admin


def test_endpoints_require_login(client):
    for path in ("/analytics/skills", "/analytics/companies", "/analytics/skill-gap", "/analytics/curriculum"):
        assert client.get(path).status_code == 401


def test_skill_gap_and_curriculum_are_admin_only(student):
    assert student.get("/analytics/skill-gap").status_code == 403
    assert student.get("/analytics/curriculum").status_code == 403
    assert student.get("/analytics/skills").status_code == 200  # demand view is open to any login


def test_top_skills_are_counted_per_posting(data):
    top = {s["skill"]: s["jobs"] for s in data.get("/analytics/skills").json()["top"]}
    assert top["python"] == 3 and top["sql"] == 1 and top["java"] == 1
    assert list(top)[0] == "python"


def test_skills_limit_and_scope(data):
    assert len(data.get("/analytics/skills", params={"limit": 2}).json()["top"]) == 2
    india = {s["skill"] for s in data.get("/analytics/skills", params={"scope": "india"}).json()["top"]}
    assert "react" not in india and "python" in india  # react is only on the remote posting
    remote = {s["skill"] for s in data.get("/analytics/skills", params={"scope": "remote"}).json()["top"]}
    assert remote == {"python", "react"}


def test_trend_has_weekly_points_for_top_skills(data):
    trend = data.get("/analytics/skills").json()["trend"]
    py = [p for p in trend if p["skill"] == "python"]
    assert py and sum(p["jobs"] for p in py) == 3 and len(py[0]["week"]) == 10


@pytest.mark.parametrize("params", [{"limit": 0}, {"weeks": 0}, {"limit": 1000}, {"scope": "mars"}])
def test_parameters_are_validated(data, params):
    assert data.get("/analytics/skills", params=params).status_code == 422


def test_skill_gap_compares_demand_with_what_students_have(data, client):
    register(client, "s1@x.edu", skills=["python"])
    register(client, "s2@x.edu", skills=["python", "sql"])
    register(client, "s3@x.edu", skills=["java"])
    r = data.get("/analytics/skill-gap").json()
    assert r["total_students"] == 3 and r["total_jobs_with_skills"] == 4
    by = {s["skill"]: s for s in r["skills"]}
    assert by["python"]["jobs"] == 3 and by["python"]["students"] == 2
    assert by["python"]["demand_pct"] == 75.0 and by["python"]["supply_pct"] == 66.7 and by["python"]["gap_pct"] == 8.3
    assert by["docker"]["students"] == 0 and by["docker"]["gap_pct"] == 25.0
    gaps = [s["gap_pct"] for s in r["skills"]]
    assert gaps == sorted(gaps, reverse=True)


def test_skill_gap_with_no_data_does_not_divide_by_zero(admin):
    r = admin.get("/analytics/skill-gap")
    assert r.status_code == 200 and r.json()["skills"] == [] and r.json()["total_jobs_with_skills"] == 0


def test_company_patterns(data):
    r = data.get("/analytics/companies").json()
    assert r["totals"] == {"active_jobs": 5, "remote": 1, "india": 3, "companies": 3}
    top = {c["company"]: c for c in r["top_companies"]}
    assert top["Acme"]["jobs"] == 2 and top["Globex"]["internships"] == 1
    assert {t["type"]: t["jobs"] for t in r["by_type"]} == {"full_time": 3, "internship": 2}
    assert {s["source"]: s["jobs"] for s in r["by_source"]} == {"shine": 2, "unstop": 2, "google": 1}
    assert sum(w["jobs"] for w in r["weekly"]) == 5


def test_inactive_postings_are_excluded(data):
    from sqlalchemy import text
    from db import engine
    with engine.begin() as c:
        c.execute(text("UPDATE job_postings SET is_active = false WHERE title = 'Dev 1'"))
    assert data.get("/analytics/companies").json()["totals"]["active_jobs"] == 4


# --- curriculum
def test_curriculum_alignment_uses_the_yaml(data, tmp_path, monkeypatch):
    f = tmp_path / "c.yaml"
    f.write_text("courses:\n  - name: Python Basics\n    skills: [Python, SQL]\n  - name: Java\n    skills: [java]\n")
    monkeypatch.setenv("CURRICULUM_FILE", str(f))
    get_settings.cache_clear()
    try:
        r = data.get("/analytics/curriculum").json()
    finally:
        monkeypatch.delenv("CURRICULUM_FILE")
        get_settings.cache_clear()
    courses = {c["course"]: c for c in r["courses"]}
    assert courses["Python Basics"]["jobs_mentioning"] == 3 and courses["Java"]["jobs_mentioning"] == 1
    # python(3) + sql(1) + java(1) taught out of 7 skill mentions (python 3, sql 1, docker 1, react 1, java 1)
    assert r["alignment_pct"] == round(100 * 5 / 7, 1)
    assert {u["skill"] for u in r["uncovered_skills"]} == {"docker", "react"}
    assert r["courses"][0]["course"] == "Python Basics"  # most-demanded course first


def test_default_curriculum_file_loads(data):
    r = data.get("/analytics/curriculum")
    assert r.status_code == 200 and len(r.json()["courses"]) >= 5


def test_broken_curriculum_gives_a_readable_error(data, tmp_path, monkeypatch):
    f = tmp_path / "bad.yaml"
    f.write_text("courses: []\n")
    monkeypatch.setenv("CURRICULUM_FILE", str(f))
    get_settings.cache_clear()
    try:
        r = data.get("/analytics/curriculum")
    finally:
        monkeypatch.delenv("CURRICULUM_FILE")
        get_settings.cache_clear()
    assert r.status_code == 500 and "curriculum.yaml" in r.json()["detail"]


@pytest.mark.parametrize("text,fragment", [
    ("not: [valid", "valid YAML"),
    ("courses:\n  - skills: [a]\n", "'name'"),
    ("courses:\n  - name: X\n", "'skills'"),
    ("", "non-empty"),
])
def test_curriculum_loader_errors(tmp_path, text, fragment):
    from curriculum import load_curriculum
    f = tmp_path / "c.yaml"
    f.write_text(text)
    with pytest.raises(ValueError, match=fragment):
        load_curriculum(f)


def test_curriculum_loader_missing_file(tmp_path):
    from curriculum import load_curriculum
    with pytest.raises(ValueError, match="not found"):
        load_curriculum(tmp_path / "nope.yaml")
