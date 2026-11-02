import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def detail_data() -> dict:
    return json.loads((FIXTURES / "detail_api.json").read_text())["data"]


@pytest.fixture
def search_data() -> dict:
    return json.loads((FIXTURES / "search_api.json").read_text())["data"]
