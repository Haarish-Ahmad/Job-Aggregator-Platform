from datetime import UTC, datetime

from scraper.config import Settings
from scraper.models import JobRecord
from scraper.storage.jsonl import JsonlStorage


def settings(monkeypatch, **env):
    for name in ("OLLAMA_HOST", "OLLAMA_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_ollama_host_is_the_primary_name(monkeypatch):
    assert settings(monkeypatch, OLLAMA_HOST="http://host.docker.internal:11434").ollama_host == "http://host.docker.internal:11434"


def test_old_ollama_url_name_still_works(monkeypatch):
    assert settings(monkeypatch, OLLAMA_URL="http://old:11434").ollama_host == "http://old:11434"


def test_ollama_host_wins_when_both_are_set(monkeypatch):
    assert settings(monkeypatch, OLLAMA_HOST="http://new:1", OLLAMA_URL="http://old:2").ollama_host == "http://new:1"


def test_default_is_local_ollama(monkeypatch):
    assert settings(monkeypatch).ollama_host == "http://localhost:11434"


def test_serve_sources_parse(monkeypatch):
    monkeypatch.setenv("SERVE_SOURCES", " unstop , shine,, ")
    assert Settings(_env_file=None).serve_source_list == ["unstop", "shine"]


def make(external_id="1", title="T", hash_="a"):
    return JobRecord(source="s", company="C", external_id=external_id, url="https://x.com/1", scraped_at=datetime.now(UTC),
                     content_hash=hash_, title=title)


def test_get_record_returns_the_latest_version_and_survives_a_restart(tmp_path):
    storage = JsonlStorage(tmp_path)
    assert storage.get_record("s", "1") is None
    storage.save(make(title="old", hash_="a"))
    storage.save(make(title="new", hash_="b"))
    assert storage.get_record("s", "1").title == "new"
    reopened = JsonlStorage(tmp_path)
    assert reopened.get_record("s", "1").title == "new" and reopened.get_hash("s", "1") == "b"
    assert reopened.get_record("s", "2") is None
