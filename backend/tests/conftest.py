"""Backend test setup. Needs a Postgres reachable at TEST_DATABASE_URL (default: localhost:5432/jobs_test), e.g.

    docker run -d --name jobs-test-pg -e POSTGRES_USER=jobs -e POSTGRES_PASSWORD=jobs -e POSTGRES_DB=jobs_test -p 5432:5432 postgres:16-alpine

The schema is built by running the real Alembic migrations, so a migration/model mismatch fails the suite.
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Must be set before the app (and its settings) are imported.
os.environ["APP_ENV"] = "dev"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql://jobs:jobs@localhost:5432/jobs_test")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["INGEST_TOKEN"] = "test-ingest-token"
os.environ["ADMIN_EMAIL"] = ""
os.environ["ADMIN_PASSWORD"] = ""

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from db import engine, session_local  # noqa: E402
from main import app  # noqa: E402

PASSWORD = "Test@1234"
INGEST_HEADERS = {"X-Ingest-Token": "test-ingest-token"}


def alembic_config() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return cfg


@pytest.fixture(scope="session", autouse=True)
def schema():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    yield


def truncate():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE matches, job_postings, company, students, scrapes RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_clean():
    """Empty tables for this test (ids restart at 1)."""
    truncate()
    yield


@pytest.fixture
def db():
    with session_local() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register(client: TestClient, email: str, **overrides):
    body = {"name": email.split("@")[0].title(), "email": email, "password": PASSWORD, "branch": "CSE", "cgpa": 8.0,
            "grad_year": 2026, "skills": ["python"], **overrides}
    r = client.post("/auth/register", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def login(client: TestClient, email: str, password: str = PASSWORD):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def make_admin(email: str):
    with engine.begin() as conn:
        conn.execute(text("UPDATE students SET role = 'admin' WHERE email = :e"), {"e": email})


@pytest.fixture
def student(client, db_clean):
    """A logged-in student."""
    register(client, "stu@snuchennai.edu.in", skills=["python", "sql"])
    login(client, "stu@snuchennai.edu.in")
    return client


@pytest.fixture
def admin(db_clean):
    """A separate logged-in admin client."""
    with TestClient(app) as c:
        register(c, "adm@snuchennai.edu.in")
        make_admin("adm@snuchennai.edu.in")
        login(c, "adm@snuchennai.edu.in")
        yield c
