import pytest
from bs4 import BeautifulSoup

from scraper.adapters.internshala import (
    InternshalaAdapter,
    parse_relative_time,
    parse_stipend,
)
from scraper.config import Settings
from scraper.models import JobRef, RawJob


@pytest.fixture
def adapter():
    return InternshalaAdapter(client=None, settings=Settings())


def test_extract_external_id(adapter):
    url = "https://internshala.com/internship/detail/flutter-dev-1790591412"
    assert adapter.extract_external_id(url) == "1790591412"
    url2 = "https://internshala.com/internship/detail/x?internship_id=12345"
    assert adapter.extract_external_id(url2) == "12345"


def test_parse_relative_time():
    result = parse_relative_time("6 days ago")
    assert result is not None
    assert len(result) == 10  # ISO date format YYYY-MM-DD
    result2 = parse_relative_time("just now")
    assert result2 is not None


def test_parse_stipend():
    result = parse_stipend("₹ 10,000 - 12,000 /month")
    assert result["currency"] == "INR"
    assert result["min"] == 10000
    assert result["max"] == 12000
    assert result["period"] == "month"

    result2 = parse_stipend("$500 - $800 /week")
    assert result2["currency"] == "USD"
    assert result2["min"] == 500
    assert result2["max"] == 800
    assert result2["period"] == "week"


def test_normalize_from_listing_fixture():
    fixture_path = "fixtures/internshala_listing.html"
    try:
        html = open(fixture_path, errors="ignore").read()
    except FileNotFoundError:
        pytest.skip("fixture not available")
    adapter = InternshalaAdapter(client=None, settings=Settings())
    soup = BeautifulSoup(html, "html.parser")
    card = soup.select_one("div.individual_internship")
    assert card
    external_id = card.get("internshipid")
    assert external_id
    href = card.get("data-href") or card.select_one("a[href*='/internship/detail']").get("href")
    raw = RawJob(
        ref=JobRef(external_id=external_id, url=f"https://internshala.com{href}", hints={}),
        content=str(card),
    )
    out = adapter.normalize(raw)
    assert out["title"]
    assert out["description_text"]
    assert out["employment_type"] == "internship"
    assert out["posted_date"]


def test_category_redirect_is_not_scraped():
    # A renamed category 301s to the generic /internships/ list, which mixes in non-software roles.
    import httpx

    class RedirectingClient:
        def request(self, method, url, **kwargs):
            return httpx.Response(200, text="<div class='individual_internship' internshipid='1'></div>",
                                  request=httpx.Request(method, "https://internshala.com/internships/"))

    adapter = InternshalaAdapter(client=RedirectingClient(), settings=Settings())
    found = {}
    adapter._search_category("/internships/software-development-internship/", 10, found)
    assert found == {}
