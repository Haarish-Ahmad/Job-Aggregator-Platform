"""Scraper ingest: token auth, per-record results, upsert on (source, external_id), legacy dedup."""
import pytest
from sqlalchemy import text

from conftest import INGEST_HEADERS, login, register
from db import engine

pytestmark = pytest.mark.usefixtures("db_clean")


def job(n=1, **kw):
    base = {"company_name": "Acme", "title": f"Software Engineer {n}", "apply_url": f"https://acme.com/jobs/{n}",
            "source": "shine", "external_id": str(n), "location": "Bengaluru", "job_type": "full_time",
            "required_skills": ["Python", " SQL "]}
    return {**base, **kw}


def post(client, jobs, headers=INGEST_HEADERS):
    return client.post("/internal/jobs", json={"jobs": jobs}, headers=headers)


def statuses(resp):
    return [r["status"] for r in resp.json()["results"]]


def count(sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


# --- authentication
def test_token_ingest_works_without_a_session(client):
    r = post(client, [job()])
    assert r.status_code == 200 and r.json()["inserted"] == 1


def test_wrong_token_is_401_and_stores_nothing(client):
    r = post(client, [job()], headers={"X-Ingest-Token": "nope"})
    assert r.status_code == 401
    assert count("SELECT count(*) FROM job_postings") == 0


def test_empty_token_header_is_rejected(client):
    assert post(client, [job()], headers={"X-Ingest-Token": ""}).status_code == 401


def test_no_credentials_is_401(client):
    assert post(client, [job()], headers={}).status_code == 401


def test_wrong_token_does_not_fall_back_to_a_student_session(client):
    register(client, "s@x.edu")
    login(client, "s@x.edu")
    assert post(client, [job()], headers={"X-Ingest-Token": "nope"}).status_code == 401


def test_admin_session_still_works(admin):
    assert post(admin, [job()], headers={}).status_code == 200


def test_student_session_is_403(student):
    assert post(student, [job()], headers={}).status_code == 403


# --- per-record behaviour
def test_response_has_a_result_per_record(client):
    r = post(client, [job(1), job(2)])
    body = r.json()
    assert (body["inserted"], body["updated"], body["skipped"], body["rejected"]) == (2, 0, 0, 0)
    assert [x["index"] for x in body["results"]] == [0, 1] and all(x["job_id"] for x in body["results"])


def test_one_bad_record_does_not_fail_or_roll_back_the_batch(client):
    r = post(client, [job(1), job(2, location="Chennai, " * 30), job(3)])
    assert r.status_code == 200
    assert statuses(r) == ["inserted", "rejected", "inserted"]
    assert "location too long" in r.json()["results"][1]["reason"]
    assert count("SELECT count(*) FROM job_postings") == 2


@pytest.mark.parametrize("field,value,fragment", [
    ("title", "T" * 256, "title too long"),
    ("apply_url", "https://x.com/" + "a" * 500, "apply_url too long"),
    ("job_type", "x" * 31, "job_type too long"),
    ("company_name", "C" * 101, "company_name too long"),
    ("external_id", "e" * 256, "external_id too long"),
    ("title", "   ", "title is blank"),
    ("company_name", "  ", "company_name is blank"),
    ("apply_url", "javascript:alert(1)", "apply_url must start with"),
    ("min_cgpa", 11, "min_cgpa"),
])
def test_invalid_records_are_rejected_with_a_reason(client, field, value, fragment):
    r = post(client, [job(**{field: value})])
    assert r.status_code == 200
    assert statuses(r) == ["rejected"] and fragment in r.json()["results"][0]["reason"]
    assert count("SELECT count(*) FROM job_postings") == 0


def test_source_without_external_id_is_rejected(client):
    r = post(client, [job(external_id=None)])
    assert statuses(r) == ["rejected"] and "together" in r.json()["results"][0]["reason"]


def test_request_shape_errors_stay_422(client):
    assert post(client, [{"company_name": "Acme", "apply_url": "https://a.com/1"}]).status_code == 422
    assert post(client, [job(posted_date="31-12-2026")]).status_code == 422


def test_batch_size_is_capped(client):
    r = post(client, [job(i) for i in range(501)])
    assert r.status_code == 422


# --- identity, upsert and freshness
def test_same_source_and_external_id_is_unchanged_the_second_time(client):
    post(client, [job()])
    again = post(client, [job()])
    assert statuses(again) == ["unchanged"] and again.json()["skipped"] == 1
    assert count("SELECT count(*) FROM job_postings") == 1


def test_changed_content_updates_in_place(client):
    first = post(client, [job(description="old text", source_content_hash="a" * 64)]).json()["results"][0]["job_id"]
    r = post(client, [job(description="new text", source_content_hash="b" * 64, required_skills=["go"])])
    assert statuses(r) == ["updated"] and r.json()["updated"] == 1
    assert r.json()["results"][0]["job_id"] == first
    assert count("SELECT count(*) FROM job_postings") == 1
    assert count("SELECT description FROM job_postings") == "new text"
    assert count("SELECT necessary_skills[1] FROM job_postings") == "go"


def test_same_hash_means_unchanged_even_if_other_fields_differ(client):
    post(client, [job(source_content_hash="a" * 64, description="one")])
    r = post(client, [job(source_content_hash="a" * 64, description="two")])
    assert statuses(r) == ["unchanged"] and count("SELECT description FROM job_postings") == "one"


def test_without_a_client_hash_the_backend_fingerprints_the_content(client):
    post(client, [job(description="a")])
    assert statuses(post(client, [job(description="a")])) == ["unchanged"]
    assert statuses(post(client, [job(description="b")])) == ["updated"]


def test_same_external_id_from_different_sources_are_different_jobs(client):
    r = post(client, [job(1, source="shine"), job(1, source="unstop")])
    assert statuses(r) == ["inserted", "inserted"]


def test_same_title_and_city_but_different_ids_are_not_collapsed(client):
    """The old company|title|location key lost these (Internshala: 777 postings -> 467)."""
    r = post(client, [job(1, title="Software Engineer"), job(2, title="Software Engineer")])
    assert statuses(r) == ["inserted", "inserted"]


def test_duplicate_inside_one_batch_is_handled(client):
    r = post(client, [job(1), job(1)])
    assert statuses(r) == ["inserted", "unchanged"]


def test_seen_again_refreshes_last_seen_and_reactivates(client):
    post(client, [job()])
    with engine.begin() as c:
        c.execute(text("UPDATE job_postings SET is_active = false, last_seen_at = now() - interval '30 days'"))
    post(client, [job()])
    assert count("SELECT is_active FROM job_postings") is True
    assert count("SELECT last_seen_at > now() - interval '1 minute' FROM job_postings") is True


def test_flags_and_dates_are_stored(client):
    post(client, [job(is_remote=True, is_india=True, work_mode="remote", posted_date="2026-10-01")])
    row = count("SELECT is_remote::text || is_india::text || work_mode || posted_date::text FROM job_postings")
    assert row == "truetrueremote2026-10-01"


# --- companies
def test_company_match_is_case_insensitive_and_careers_url_is_the_site(client):
    post(client, [job(1, company_name="Acme Corp"), job(2, company_name="ACME CORP ")])
    assert count("SELECT count(*) FROM company") == 1
    assert count("SELECT careers_url FROM company") == "https://acme.com/"


# --- legacy payloads (no source) keep the old behaviour
def test_legacy_payload_dedups_on_company_title_location(client):
    legacy = {"company_name": "Zoho", "title": "Backend Intern", "apply_url": "https://z.com/1", "location": "Chennai"}
    assert post(client, [legacy]).json()["inserted"] == 1
    again = post(client, [{**legacy, "apply_url": "https://z.com/other"}])
    assert (again.json()["inserted"], again.json()["skipped"]) == (0, 1)
    assert count("SELECT source FROM job_postings") is None


def test_admin_cookie_and_token_can_both_ingest_the_same_data(admin, client):
    post(admin, [job()], headers={})
    assert statuses(post(client, [job()])) == ["unchanged"]
