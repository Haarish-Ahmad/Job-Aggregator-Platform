from datetime import UTC, datetime

from scraper.config import Settings
from scraper.models import JobRecord
from scraper.storage.jsonl import JsonlStorage


def test_leftover_ollama_settings_in_an_old_env_file_are_ignored(monkeypatch):
    """Existing deployments still have OLLAMA_* and SERVE_EXTRACT in their .env: that must not break start-up."""
    for name, value in {"OLLAMA_HOST": "http://old:11434", "OLLAMA_MODEL": "qwen2.5:3b", "SERVE_EXTRACT": "true"}.items():
        monkeypatch.setenv(name, value)
    settings = Settings(_env_file=None)
    assert not hasattr(settings, "ollama_host") and not hasattr(settings, "serve_extract")


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
