"""All 42 cases from backend/testcases.md, in the same order and with the same data.

The spec cases depend on each other (later ones use earlier data and the logged-in user), so they share
module-scoped state and must run top to bottom. The one deliberate difference: the spec's hardcoded
deadline "2026-12-31" is replaced by a date one year from today so the suite does not expire.
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from conftest import PASSWORD, truncate
from db import engine
from main import app

FUTURE = (date.today() + timedelta(days=365)).isoformat()
ASHA = {"name": "Asha", "email": "asha@snuchennai.edu.in", "password": PASSWORD, "branch": "CSE", "cgpa": 8.5,
        "grad_year": 2026, "skills": ["python", "sql", "docker"]}
RAVI = {"name": "Ravi", "email": "ravi@snuchennai.edu.in", "password": PASSWORD, "branch": "ECE", "cgpa": 6.5,
        "grad_year": 2027, "skills": ["java"]}
ZOHO = {"company_name": "Zoho", "careers_url": "https://www.zoho.com/careers", "description": "Software company"}
JOBS = [
    {"company_name": "Zoho", "title": "Backend Intern", "apply_url": "https://zoho.com/j/1", "location": "Chennai",
     "job_type": "internship", "description": "FastAPI work", "min_cgpa": 7.0, "allowed_branches": ["CSE", "IT"],
     "allowed_grads": [2026, 2027], "required_skills": ["python", "sql"], "deadline": FUTURE},
    {"company_name": "Zoho", "title": "High CGPA Role", "apply_url": "https://zoho.com/j/2", "min_cgpa": 9.5,
     "required_skills": ["python"], "deadline": FUTURE},
    {"company_name": "Zoho", "title": "Expired Role", "apply_url": "https://zoho.com/j/3", "required_skills": ["python"],
     "deadline": "2020-01-01"},
    {"company_name": "Zoho", "title": "ECE Only", "apply_url": "https://zoho.com/j/4", "allowed_branches": ["ECE"],
     "required_skills": ["java"], "deadline": FUTURE},
    {"company_name": "Infosys", "title": "Open Role", "apply_url": "https://infosys.com/j/5", "required_skills": [],
     "deadline": FUTURE},
    {"company_name": "Infosys", "title": "Half Match", "apply_url": "https://infosys.com/j/6",
     "required_skills": ["python", "kubernetes"], "deadline": FUTURE},
]
ONE_JOB = {"jobs": [{"company_name": "Zoho", "title": "T", "apply_url": "https://z.com/0"}]}


@pytest.fixture(scope="module")
def world():
    truncate()
    with TestClient(app) as anon, TestClient(app) as asha, TestClient(app) as ravi:
        yield {"anon": anon, "asha": asha, "ravi": ravi}


def titles(resp):
    return sorted(j["title"] for j in resp.json())


def scores(resp):
    return {m["job"]["title"]: m["score"] for m in resp.json()}


# --- Health and access
def test_tc01_server_is_up(world):
    assert world["anon"].get("/health").status_code == 200


def test_tc02_profile_without_login(world):
    assert world["anon"].get("/me").status_code == 401


# --- Register
def test_tc03_register_asha(world):
    r = world["anon"].post("/auth/register", json=ASHA)
    assert r.status_code == 201
    assert r.json()["role"] == "student" and r.json()["id"]
    assert "password" not in r.text and "password_hash" not in r.text


def test_tc04_register_ravi(world):
    assert world["anon"].post("/auth/register", json=RAVI).status_code == 201


def test_tc05_duplicate_email(world):
    assert world["anon"].post("/auth/register", json=ASHA).status_code == 409
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM students WHERE email = :e"), {"e": ASHA["email"]}).scalar() == 1


def test_tc06_invalid_email(world):
    r = world["anon"].post("/auth/register", json={"name": "X", "email": "abc", "password": PASSWORD, "grad_year": 2026})
    assert r.status_code == 422


def test_tc07_missing_grad_year(world):
    r = world["anon"].post("/auth/register", json={"name": "X", "email": "x@snuchennai.edu.in", "password": PASSWORD})
    assert r.status_code == 422


# --- Login and session
def test_tc08_wrong_password(world):
    r = world["anon"].post("/auth/login", json={"email": ASHA["email"], "password": "wrong"})
    assert r.status_code == 401 and "set-cookie" not in r.headers


def test_tc09_unknown_email_same_response_as_wrong_password(world):
    wrong = world["anon"].post("/auth/login", json={"email": ASHA["email"], "password": "wrong"})
    unknown = world["anon"].post("/auth/login", json={"email": "nobody@snuchennai.edu.in", "password": "x"})
    assert unknown.status_code == 401 and unknown.json() == wrong.json()


def test_tc10_login_asha(world):
    r = world["asha"].post("/auth/login", json={"email": ASHA["email"], "password": PASSWORD})
    assert r.status_code == 200 and r.json()["email"] == ASHA["email"]
    assert "session=" in r.headers["set-cookie"]


def test_tc11_read_own_profile(world):
    r = world["asha"].get("/me")
    assert r.status_code == 200 and r.json()["name"] == "Asha" and "password" not in r.text


# --- Update profile
def test_tc12_update_cgpa_and_skills(world):
    r = world["asha"].patch("/me/update", json={"cgpa": 9.0, "skills": ["python", "sql", "docker", "react"]})
    assert r.status_code == 200
    body = r.json()
    assert body["cgpa"] == 9.0 and body["skills"] == ["python", "sql", "docker", "react"]
    assert (body["name"], body["branch"], body["grad_year"]) == ("Asha", "CSE", 2026)


def test_tc13_empty_body(world):
    before = world["asha"].get("/me").json()
    assert world["asha"].patch("/me/update", json={}).status_code == 200
    assert world["asha"].get("/me").json() == before


def test_tc14_try_to_set_role(world):
    assert world["asha"].patch("/me/update", json={"role": "admin"}).status_code == 200
    assert world["asha"].get("/me").json()["role"] == "student"


def test_tc15_try_to_change_email(world):
    assert world["asha"].patch("/me/update", json={"email": "hacker@x.com"}).status_code == 200
    assert world["asha"].get("/me").json()["email"] == ASHA["email"]


def test_tc16_invalid_cgpa(world):
    assert world["asha"].patch("/me/update", json={"cgpa": 11}).status_code == 422


# --- Companies
def test_tc17_create_company(world):
    r = world["asha"].post("/company", json=ZOHO)
    assert r.status_code == 201 and r.json()["id"] == 1


def test_tc18_duplicate_company(world):
    assert world["asha"].post("/company", json=ZOHO).status_code == 409


def test_tc19_list_companies(world):
    r = world["asha"].get("/companies")
    assert r.status_code == 200 and "Zoho" in [c["company_name"] for c in r.json()]


# --- Job ingestion (admin only)
def test_tc20_ingest_as_student(world):
    assert world["asha"].post("/internal/jobs", json=ONE_JOB).status_code == 403


def test_tc21_ingest_six_jobs(world):
    with engine.begin() as c:
        c.execute(text("UPDATE students SET role = 'admin' WHERE email = :e"), {"e": ASHA["email"]})
    world["asha"].post("/auth/login", json={"email": ASHA["email"], "password": PASSWORD})  # session picks up the role
    r = world["asha"].post("/internal/jobs", json={"jobs": JOBS})
    assert r.status_code == 200
    assert (r.json()["inserted"], r.json()["skipped"]) == (6, 0)
    names = [c["company_name"] for c in world["asha"].get("/companies").json()]
    assert "Infosys" in names  # created automatically


def test_tc22_ingest_same_payload_again(world):
    r = world["asha"].post("/internal/jobs", json={"jobs": JOBS})
    assert r.status_code == 200 and (r.json()["inserted"], r.json()["skipped"]) == (0, 6)


def test_tc23_missing_title(world):
    r = world["asha"].post("/internal/jobs", json={"jobs": [{"company_name": "Zoho", "apply_url": "https://z.com/9"}]})
    assert r.status_code == 422


def test_tc24_bad_deadline_format(world):
    job = {"company_name": "Zoho", "title": "X", "apply_url": "https://z.com/9", "deadline": "31-12-2026"}
    assert world["asha"].post("/internal/jobs", json={"jobs": [job]}).status_code == 422


# --- Job listing
def test_tc25_all_jobs(world):
    r = world["asha"].get("/jobs")
    assert r.status_code == 200 and len(r.json()) == 6


def test_tc26_search_text(world):
    assert titles(world["asha"].get("/jobs", params={"q": "backend"})) == ["Backend Intern"]


def test_tc27_filter_by_company(world):
    r = world["asha"].get("/jobs", params={"company_id": 1})
    assert titles(r) == ["Backend Intern", "ECE Only", "Expired Role", "High CGPA Role"]


def test_tc28_filter_by_type(world):
    assert titles(world["asha"].get("/jobs", params={"job_type": "internship"})) == ["Backend Intern"]


def test_tc29_pagination(world):
    everything = [j["id"] for j in world["asha"].get("/jobs").json()]
    r = world["asha"].get("/jobs", params={"limit": 2, "offset": 2})
    assert r.status_code == 200 and [j["id"] for j in r.json()] == everything[2:4]


def test_tc30_limit_above_maximum_is_clamped(world):
    r = world["asha"].get("/jobs", params={"limit": 500})
    assert r.status_code == 200 and len(r.json()) <= 100


def test_tc31_job_by_id(world):
    r = world["asha"].get("/jobs/1")
    assert r.status_code == 200 and r.json()["id"] == 1


def test_tc32_job_not_found(world):
    assert world["asha"].get("/jobs/9999").status_code == 404


def test_tc33_invalid_id(world):
    assert world["asha"].get("/jobs/abc").status_code == 422


# --- Matching
def test_tc34_asha_matches(world):
    r = world["asha"].get("/me/matches")
    assert r.status_code == 200
    assert scores(r) == {"Backend Intern": 100.0, "Open Role": 100.0, "Half Match": 50.0}
    ranked = [m["score"] for m in r.json()]
    assert ranked == sorted(ranked, reverse=True)


def test_tc35_minimum_score_filter(world):
    assert "Half Match" not in scores(world["asha"].get("/me/matches", params={"min_score": 60}))


def test_tc36_idempotent_save(world):
    world["asha"].get("/me/matches")
    assert world["asha"].get("/me/matches").status_code == 200
    with engine.connect() as c:
        dupes = c.execute(text("SELECT count(*) FROM (SELECT 1 FROM matches GROUP BY student_id, job_id HAVING count(*) > 1) t")).scalar()
    assert dupes == 0


def test_tc37_ravi_matches(world):
    world["ravi"].post("/auth/login", json={"email": RAVI["email"], "password": PASSWORD})
    r = world["ravi"].get("/me/matches")
    assert r.status_code == 200
    assert scores(r) == {"ECE Only": 100.0, "Open Role": 100.0}  # Half Match (0%) is hidden by default


def test_tc37b_include_unmatched_shows_zero_percent(world):
    r = world["ravi"].get("/me/matches", params={"include_unmatched": "true"})
    assert scores(r) == {"ECE Only": 100.0, "Open Role": 100.0, "Half Match": 0.0}


def test_tc38_ravi_cannot_ingest(world):
    assert world["ravi"].post("/internal/jobs", json=ONE_JOB).status_code == 403


# --- Logout
def test_tc39_logout(world):
    assert world["asha"].post("/auth/logout").status_code == 200


def test_tc40_profile_after_logout(world):
    assert world["asha"].get("/me").status_code == 401


def test_tc41_jobs_after_logout(world):
    assert world["asha"].get("/jobs").status_code == 401


def test_tc42_matches_after_logout(world):
    assert world["asha"].get("/me/matches").status_code == 401
