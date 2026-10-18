"""/jobs filters, sorting, pagination validation, total count; auth on formerly public routes."""
from datetime import date, timedelta

import pytest

from conftest import INGEST_HEADERS

pytestmark = pytest.mark.usefixtures("db_clean")


def seed(client, jobs):
    r = client.post("/internal/jobs", json={"jobs": jobs}, headers=INGEST_HEADERS)
    assert r.status_code == 200 and r.json()["rejected"] == 0, r.text


def job(n, **kw):
    return {"company_name": "Acme", "title": f"Role {n}", "apply_url": f"https://acme.com/{n}", "source": "shine",
            "external_id": str(n), **kw}


def titles(r):
    return [j["title"] for j in r.json()]


@pytest.fixture
def catalog(student):
    seed(student, [
        job(1, title="Python Developer", location="Pune, India", is_india=True, required_skills=["python"],
            job_type="full_time", allowed_grads=[2026]),
        job(2, title="Remote React Engineer", company_name="Globex", location="Work from home", is_remote=True,
            required_skills=["react"], job_type="internship", source="internshala", allowed_grads=[2027]),
        job(3, title="Data Analyst", location="Mumbai, India", is_india=True, required_skills=["sql", "excel"],
            job_type="full_time", deadline=(date.today() - timedelta(days=1)).isoformat()),
        job(4, title="US Only Role", company_name="Initech", location="Austin, TX", is_india=False, source="google"),
    ])
    return student


# --- pagination validation: 422, not 500
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": -1}, {"offset": -1}, {"limit": "abc"}])
def test_bad_pagination_is_422(student, params):
    assert student.get("/jobs", params=params).status_code == 422


def test_limit_over_100_clamps_to_100(student):
    assert student.get("/jobs", params={"limit": 5000}).status_code == 200


def test_total_count_header_ignores_limit(catalog):
    r = catalog.get("/jobs", params={"limit": 1})
    assert len(r.json()) == 1 and r.headers["x-total-count"] == "4"


# --- filters
def test_scope_filters(catalog):
    assert sorted(titles(catalog.get("/jobs", params={"scope": "india"}))) == ["Data Analyst", "Python Developer"]
    assert titles(catalog.get("/jobs", params={"scope": "remote"})) == ["Remote React Engineer"]
    assert len(catalog.get("/jobs", params={"scope": "india_remote"}).json()) == 3
    assert len(catalog.get("/jobs").json()) == 4  # default stays "all"


def test_search_matches_title_or_company(catalog):
    assert titles(catalog.get("/jobs", params={"q": "python"})) == ["Python Developer"]
    assert titles(catalog.get("/jobs", params={"q": "globex"})) == ["Remote React Engineer"]


def test_search_wildcards_are_literal(catalog):
    assert catalog.get("/jobs", params={"q": "%"}).json() == []
    assert catalog.get("/jobs", params={"q": "_"}).json() == []


def test_location_skill_source_and_type_filters(catalog):
    assert titles(catalog.get("/jobs", params={"location": "pune"})) == ["Python Developer"]
    assert titles(catalog.get("/jobs", params={"skill": "SQL"})) == ["Data Analyst"]
    assert titles(catalog.get("/jobs", params={"source": "internshala"})) == ["Remote React Engineer"]
    assert titles(catalog.get("/jobs", params={"job_type": "internship"})) == ["Remote React Engineer"]


def test_grad_year_includes_jobs_open_to_any_year(catalog):
    got = titles(catalog.get("/jobs", params={"grad_year": 2026}))
    assert "Python Developer" in got and "Data Analyst" in got and "Remote React Engineer" not in got


def test_hide_expired(catalog):
    assert "Data Analyst" in titles(catalog.get("/jobs"))
    assert "Data Analyst" not in titles(catalog.get("/jobs", params={"hide_expired": "true"}))


def test_inactive_jobs_hidden_unless_asked(catalog):
    from sqlalchemy import text
    from db import engine
    with engine.begin() as c:
        c.execute(text("UPDATE job_postings SET is_active = false WHERE title = 'US Only Role'"))
    assert "US Only Role" not in titles(catalog.get("/jobs"))
    assert "US Only Role" in titles(catalog.get("/jobs", params={"active_only": "false"}))


# --- sorting
def test_sorting(catalog):
    assert titles(catalog.get("/jobs", params={"sort": "title"})) == sorted(titles(catalog.get("/jobs")), key=str.lower)
    newest = catalog.get("/jobs", params={"sort": "newest"}).json()
    oldest = catalog.get("/jobs", params={"sort": "oldest"}).json()
    assert [j["id"] for j in newest] == [j["id"] for j in reversed(oldest)]
    assert catalog.get("/jobs", params={"sort": "nonsense"}).status_code == 422


def test_deadline_sort_puts_jobs_without_deadline_last(catalog):
    assert titles(catalog.get("/jobs", params={"sort": "deadline"}))[0] == "Data Analyst"


# --- shape
def test_job_out_includes_company_and_freshness_fields(catalog):
    j = catalog.get("/jobs", params={"q": "python"}).json()[0]
    assert j["company_name"] == "Acme" and j["source"] == "shine" and j["external_id"] == "1"
    assert j["scraped_at"] and j["last_seen_at"] and j["is_india"] is True and j["is_remote"] is False


# --- auth that the README promised
@pytest.mark.parametrize("method,path", [("post", "/company"), ("get", "/companies"), ("get", "/jobs/1"), ("get", "/jobs")])
def test_routes_require_login(client, method, path):
    kwargs = {"json": {"company_name": "X", "careers_url": "https://x.com"}} if method == "post" else {}
    assert getattr(client, method)(path, **kwargs).status_code == 401
