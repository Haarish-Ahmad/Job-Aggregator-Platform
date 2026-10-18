import pytest
from fastapi.testclient import TestClient

from conftest import INGEST_HEADERS
from main import app

pytestmark = pytest.mark.usefixtures("db_clean")


def test_health_checks_the_database(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "db": "ok"}


def test_health_is_503_when_the_database_is_down(monkeypatch):
    from db import get_db

    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("down")

    app.dependency_overrides[get_db] = lambda: Broken()
    try:
        with TestClient(app) as c:
            assert c.get("/health").status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_metrics_use_route_templates_not_raw_paths(client, student):
    student.get("/jobs/12345")
    text = client.get("/metrics").text
    assert 'route="/jobs/{job_id}"' in text and "12345" not in text
    assert "http_request_duration_seconds_bucket" in text
    assert 'status="404"' in text


def test_metrics_count_ingest_outcomes_and_report_gauges(client):
    client.post("/internal/jobs", headers=INGEST_HEADERS, json={"jobs": [
        {"company_name": "A", "title": "T", "apply_url": "https://a.com/1", "source": "shine", "external_id": "1"},
        {"company_name": "A", "title": "", "apply_url": "https://a.com/2"}]})
    text = client.get("/metrics").text
    assert 'ingest_records_total{status="inserted"}' in text and 'ingest_records_total{status="rejected"}' in text
    assert 'jobs_active{source="shine"} 1.0' in text and "students_total" in text


def test_metrics_endpoint_is_hidden_from_the_api_docs(client):
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]


def test_5xx_responses_are_counted(client):
    from db import get_db

    def boom():
        raise RuntimeError("db exploded")

    app.dependency_overrides[get_db] = boom
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            assert c.get("/jobs").status_code == 500
    finally:
        app.dependency_overrides.clear()
    assert "http_server_errors_total" in client.get("/metrics").text
