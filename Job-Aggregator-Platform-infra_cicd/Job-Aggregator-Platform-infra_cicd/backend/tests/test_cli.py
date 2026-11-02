"""Operational commands: admin bootstrap, stale-job deactivation."""
import pytest
from sqlalchemy import text

import cli
from config import get_settings
from conftest import INGEST_HEADERS, login
from db import engine

pytestmark = pytest.mark.usefixtures("db_clean")


@pytest.fixture
def env(monkeypatch):
    def set_env(**kw):
        for k, v in kw.items():
            monkeypatch.setenv(k.upper(), v)
        get_settings.cache_clear()
    yield set_env
    get_settings.cache_clear()


def test_bootstrap_skips_when_not_configured(env, client):
    env(admin_email="", admin_password="")
    assert cli.bootstrap_admin() == 0
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM students")).scalar() == 0


def test_bootstrap_creates_an_admin_who_can_log_in_and_ingest(env, client):
    env(admin_email="boss@college.edu", admin_password="s3cretpass")
    assert cli.bootstrap_admin() == 0
    me = login(client, "boss@college.edu", "s3cretpass")
    assert me["role"] == "admin"
    r = client.post("/internal/jobs", json={"jobs": [{"company_name": "A", "title": "T", "apply_url": "https://a.com/1"}]})
    assert r.status_code == 200


def test_bootstrap_is_idempotent_and_updates_the_password(env, client):
    env(admin_email="boss@college.edu", admin_password="firstpass1")
    cli.bootstrap_admin()
    env(admin_email="boss@college.edu", admin_password="secondpass2")
    cli.bootstrap_admin()
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM students")).scalar() == 1
    assert client.post("/auth/login", json={"email": "boss@college.edu", "password": "firstpass1"}).status_code == 401
    assert client.post("/auth/login", json={"email": "boss@college.edu", "password": "secondpass2"}).status_code == 200


def test_bootstrap_promotes_an_existing_student(env, client):
    from conftest import register
    register(client, "boss@college.edu")
    env(admin_email="boss@college.edu", admin_password="newpass123")
    cli.bootstrap_admin()
    assert login(client, "boss@college.edu", "newpass123")["role"] == "admin"


def test_bootstrap_rejects_a_short_password(env):
    env(admin_email="boss@college.edu", admin_password="short")
    assert cli.bootstrap_admin() == 1


def test_deactivate_stale_only_touches_old_scraped_postings(env, client):
    jobs = [{"company_name": "A", "title": f"T{i}", "apply_url": f"https://a.com/{i}", "source": "shine", "external_id": str(i)} for i in range(3)]
    jobs.append({"company_name": "A", "title": "Manual", "apply_url": "https://a.com/m"})  # no source
    client.post("/internal/jobs", json={"jobs": jobs}, headers=INGEST_HEADERS)
    with engine.begin() as c:
        c.execute(text("UPDATE job_postings SET last_seen_at = now() - interval '30 days' WHERE title IN ('T0', 'Manual')"))
    env(stale_days="14")
    assert cli.deactivate_stale() == 0
    with engine.connect() as c:
        rows = dict(c.execute(text("SELECT title, is_active FROM job_postings")).all())
    assert rows == {"T0": False, "T1": True, "T2": True, "Manual": True}


def test_main_dispatches_commands(env):
    env(admin_email="", admin_password="")
    assert cli.main(["bootstrap-admin"]) == 0
    with pytest.raises(SystemExit):
        cli.main(["nonsense"])


@pytest.mark.parametrize("email", ["admin@example.test", "admin@localhost", "not-an-email"])
def test_bootstrap_rejects_an_email_the_login_form_would_reject(env, client, email):
    env(admin_email=email, admin_password="goodpassword1")
    assert cli.bootstrap_admin() == 1
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM students")).scalar() == 0
