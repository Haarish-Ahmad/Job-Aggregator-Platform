"""Email alerts: opt-in, one digest per student, notified_at bookkeeping, failure isolation."""
import pytest
from fastapi.testclient import TestClient

import alerts
from config import get_settings
from conftest import INGEST_HEADERS, login, register
from main import app
from models import Match

pytestmark = pytest.mark.usefixtures("db_clean")


def seed_jobs(client):
    jobs = [{"company_name": "Acme", "title": f"Python Role {i}", "apply_url": f"https://acme.com/{i}",
             "source": "shine", "external_id": str(i), "required_skills": ["python"]} for i in range(3)]
    jobs.append({"company_name": "Acme", "title": "Rust Role", "apply_url": "https://acme.com/rust", "source": "shine",
                 "external_id": "rust", "required_skills": ["rust", "c", "go", "zig"]})
    assert client.post("/internal/jobs", json={"jobs": jobs}, headers=INGEST_HEADERS).status_code == 200


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "send_email", lambda msg, settings: sent.append(msg))
    return sent


def subscribe(client, email="a@x.edu", skills=("python",), enabled=True):
    register(client, email, skills=list(skills))
    login(client, email)
    client.patch("/me/update", json={"alerts_enabled": enabled})


def test_opt_in_flag_is_saved_and_defaults_off(client):
    register(client, "a@x.edu")
    login(client, "a@x.edu")
    assert client.get("/me").json()["alerts_enabled"] is False
    assert client.patch("/me/update", json={"alerts_enabled": True}).json()["alerts_enabled"] is True


def test_students_who_did_not_opt_in_get_nothing(client, outbox):
    seed_jobs(client)
    subscribe(client, enabled=False)
    r = client.post("/internal/alerts/run", headers=INGEST_HEADERS)
    assert r.status_code == 200 and r.json()["emails_sent"] == 0 and outbox == []


def test_one_digest_lists_good_matches_only(client, outbox):
    seed_jobs(client)
    subscribe(client)
    r = client.post("/internal/alerts/run", headers=INGEST_HEADERS).json()
    assert (r["students"], r["emails_sent"], r["matches_notified"]) == (1, 1, 3)
    msg = outbox[0]
    assert msg["To"] == "a@x.edu" and "3 new job matches" in msg["Subject"]
    body = msg.get_content()
    assert "Python Role 0" in body and "Rust Role" not in body and "/jobs/" in body


def test_matches_are_marked_notified_and_never_resent(client, outbox, db):
    seed_jobs(client)
    subscribe(client)
    client.post("/internal/alerts/run", headers=INGEST_HEADERS)
    assert db.query(Match).filter(Match.notified_at.is_(None), Match.score >= 60).count() == 0
    again = client.post("/internal/alerts/run", headers=INGEST_HEADERS).json()
    assert again["emails_sent"] == 0 and len(outbox) == 1


def test_new_jobs_trigger_a_new_digest(client, outbox):
    seed_jobs(client)
    subscribe(client)
    client.post("/internal/alerts/run", headers=INGEST_HEADERS)
    client.post("/internal/jobs", headers=INGEST_HEADERS, json={"jobs": [
        {"company_name": "Acme", "title": "Brand New", "apply_url": "https://acme.com/new", "source": "shine",
         "external_id": "new", "required_skills": ["python"]}]})
    client.post("/internal/alerts/run", headers=INGEST_HEADERS)
    assert len(outbox) == 2 and "1 new job match " in outbox[1]["Subject"] + " "


def test_score_threshold_is_respected(client, outbox, monkeypatch):
    seed_jobs(client)
    subscribe(client, skills=("python", "rust"))  # Rust Role scores 25% (1 of 4 skills)
    monkeypatch.setenv("ALERT_MIN_SCORE", "20")
    get_settings.cache_clear()
    try:
        client.post("/internal/alerts/run", headers=INGEST_HEADERS)
        assert "Rust Role" in outbox[0].get_content()
    finally:
        monkeypatch.delenv("ALERT_MIN_SCORE")
        get_settings.cache_clear()


def test_smtp_failure_for_one_student_does_not_stop_the_others(client, monkeypatch, db):
    seed_jobs(client)
    subscribe(client, "bad@x.edu")
    with TestClient(app) as other:
        subscribe(other, "good@x.edu")
    sent = []

    def flaky(msg, settings):
        if msg["To"] == "bad@x.edu":
            raise ConnectionRefusedError("smtp down")
        sent.append(msg["To"])

    monkeypatch.setattr(alerts, "send_email", flaky)
    r = client.post("/internal/alerts/run", headers=INGEST_HEADERS).json()
    assert (r["emails_sent"], r["emails_failed"]) == (1, 1) and sent == ["good@x.edu"]
    # The failed student's matches stay un-notified so the next run retries them.
    assert db.query(Match).filter(Match.notified_at.is_(None), Match.score >= 60).count() == 3


def test_alert_run_requires_credentials(client, student):
    assert client.post("/internal/alerts/run").status_code == 403  # logged in as a student
    with TestClient(app) as anon:
        assert anon.post("/internal/alerts/run").status_code == 401


def test_message_caps_the_number_of_jobs():
    from types import SimpleNamespace as NS
    settings = get_settings()
    student = NS(name="Asha", email="a@x.edu")
    rows = [(NS(score=90.0), NS(id=i, title=f"J{i}", company_name="Co")) for i in range(settings.alert_max_jobs_per_email + 5)]
    body = alerts.build_message(student, rows, settings).get_content()
    assert "and 5 more" in body and body.count("/jobs/") == settings.alert_max_jobs_per_email
