import json
import re

import pytest

from scraper.adapters.microsoft import MicrosoftAdapter
from scraper.config import Settings
from scraper.http import PoliteClient
from scraper.models import SearchFilters
from scraper.pipeline import run
from scraper.storage.jsonl import JsonlStorage


def _page(ids, count):
    return {"data": {"count": count, "positions": [
        {"id": i, "name": f"Job {i} INTERN", "positionUrl": f"/careers/job/{i}"} for i in ids]}}


@pytest.fixture
def client(httpx_mock):
    httpx_mock.add_response(url="https://apply.careers.microsoft.com/robots.txt",
                            text="User-agent: *\nDisallow: /\nAllow: /api/pcsx\n", is_reusable=True)
    c = PoliteClient("test", delay_seconds=0)
    yield c
    c.close()


def test_discover_paginates_and_respects_limit(httpx_mock, client):
    httpx_mock.add_response(url=re.compile(r".*search.*start=0.*"), json=_page([1, 2, 3], 5))
    httpx_mock.add_response(url=re.compile(r".*search.*start=3.*"), json=_page([4, 5], 5))
    adapter = MicrosoftAdapter(client, Settings())
    refs = adapter.discover(SearchFilters(queries=["intern"], locations=["India"], limit=4))
    assert [r.external_id for r in refs] == ["1", "2", "3", "4"]


def test_discover_dedupes_across_queries(httpx_mock, client):
    httpx_mock.add_response(url=re.compile(r".*search.*"), json=_page([1, 2], 2), is_reusable=True)
    adapter = MicrosoftAdapter(client, Settings())
    refs = adapter.discover(SearchFilters(queries=["a", "b"], locations=["India"], limit=10))
    assert [r.external_id for r in refs] == ["1", "2"]


def test_pipeline_saves_skips_unchanged_and_isolates_failures(httpx_mock, client, tmp_path, detail_data):
    httpx_mock.add_response(url=re.compile(r".*search.*"), json=_page([1, 2], 2), is_reusable=True)
    httpx_mock.add_response(url=re.compile(r".*position_id=1&.*"), json={"data": detail_data}, is_reusable=True)
    httpx_mock.add_response(url=re.compile(r".*position_id=2&.*"), status_code=404, is_reusable=True)
    adapter = MicrosoftAdapter(client, Settings(max_concurrency=1))
    storage = JsonlStorage(tmp_path)
    filters = SearchFilters(queries=["intern"], locations=["India"], limit=10)

    first = run(adapter, filters, storage, Settings(max_concurrency=1))
    assert (first.saved, first.failed) == (1, 1)
    assert json.loads(storage.dead_letter_path.read_text())["external_id"] == "2"

    second = run(adapter, filters, JsonlStorage(tmp_path), Settings(max_concurrency=1))
    assert (second.saved, second.unchanged) == (0, 1)
    assert len((tmp_path / "jobs.jsonl").read_text().splitlines()) == 1
