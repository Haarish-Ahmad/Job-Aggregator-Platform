"""Startup safety: production refuses to run with missing/default secrets; dev stays convenient."""
import pytest
from pydantic import ValidationError

from config import DEV_SECRET_KEY, Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """conftest sets SECRET_KEY / DATABASE_URL for the app; these tests need to start from nothing."""
    for name in ("SECRET_KEY", "DATABASE_URL", "APP_ENV", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)


def make(**kw):
    return Settings(_env_file=None, **kw)


def test_production_requires_a_secret_key():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        make(app_env="production", secret_key="", database_url="postgresql://u:p@db/x")


def test_production_rejects_the_default_secret_key():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        make(app_env="production", secret_key=DEV_SECRET_KEY, database_url="postgresql://u:p@db/x")


def test_unknown_env_is_treated_as_production():
    with pytest.raises(ValidationError):
        make(app_env="staging", secret_key="", database_url="postgresql://u:p@db/x")


def test_production_requires_database_url():
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        make(app_env="production", secret_key="real-secret", database_url="")


def test_production_default_env_is_production():
    with pytest.raises(ValidationError):
        make(secret_key="", database_url="")


def test_dev_fills_in_defaults():
    s = make(app_env="dev")
    assert s.secret_key == DEV_SECRET_KEY and s.database_url.startswith("postgresql://") and s.is_dev


def test_production_accepts_real_values():
    s = make(app_env="production", secret_key="x" * 32, database_url="postgresql://u:p@db/x")
    assert not s.is_dev


def test_cors_origins_come_from_env_and_are_trimmed():
    s = make(app_env="dev", cors_origins=" http://a.test , http://b.test,, ")
    assert s.cors_origin_list == ["http://a.test", "http://b.test"]


def test_cors_only_allows_configured_origins(client):
    ok = client.options("/jobs", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    bad = client.options("/jobs", headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers
