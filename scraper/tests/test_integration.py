import pytest

from scraper.adapters.microsoft import MicrosoftAdapter
from scraper.config import Settings
from scraper.http import PoliteClient
from scraper.models import SearchFilters
from scraper.pipeline import build_record
from datetime import UTC, datetime


@pytest.mark.integration
def test_live_microsoft_end_to_end():
    settings = Settings()
    client = PoliteClient(settings.user_agent, settings.request_delay_seconds)
    try:
        adapter = MicrosoftAdapter(client, settings)
        refs = adapter.discover(SearchFilters(queries=["intern"], locations=["India"], limit=2))
        assert refs
        record = build_record(adapter, adapter.fetch(refs[0]), datetime.now(UTC))
        assert record.title and record.description_text
    finally:
        client.close()
