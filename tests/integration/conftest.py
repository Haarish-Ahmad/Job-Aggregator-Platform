"""Integration tests: the real scraper pipeline talking to the real backend app (in-process) and Postgres.

Needs a Postgres at TEST_DATABASE_URL (default localhost:5432/jobs_test) and both packages installed:
    pip install -r requirements-dev.txt && pip install -e "scraper[dev]"
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

os.environ["APP_ENV"] = "dev"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql://jobs:jobs@localhost:5432/jobs_test")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["INGEST_TOKEN"] = "test-ingest-token"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from db import engine  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def clean_tables():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE matches, job_postings, company, students, scrapes RESTART IDENTITY CASCADE"))


@pytest.fixture
def backend():
    """The backend as an httpx client: used by the scraper to push, and (separately) by a student to read."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def student():
    with TestClient(app) as c:
        body = {"name": "Stu", "email": "stu@college.edu", "password": "Test@1234", "grad_year": 2026, "skills": ["python"]}
        assert c.post("/auth/register", json=body).status_code == 201
        assert c.post("/auth/login", json={"email": body["email"], "password": body["password"]}).status_code == 200
        yield c
