import re

from scraper.adapters.base import SourceAdapter
from scraper.models import JobRef, RawJob
from scraper.preprocess import clean_markdown, truncate


class FirecrawlAdapter(SourceAdapter):
    """Base for sites with no usable API: Firecrawl renders the page, we clean the markdown.

    A concrete site subclass only has to implement discover() and extract_external_id(),
    and may override the scrape options below. discover() can call scrape() to render
    listing pages the same way fetch() renders a posting.
    """

    wait_for_ms = 3000
    only_main_content = True

    def scrape(self, url: str) -> str:
        """Render `url` with Firecrawl and return cleaned markdown (robots.txt is checked on `url`)."""
        headers = {"Content-Type": "application/json"}
        if self.settings.firecrawl_api_key:
            headers["Authorization"] = f"Bearer {self.settings.firecrawl_api_key}"
        resp = self.client.request(
            "POST",
            f"{self.settings.firecrawl_api_url.rstrip('/')}/v2/scrape",
            robots_target=url,
            headers=headers,
            timeout=90,
            json={
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": self.only_main_content,
                "waitFor": self.wait_for_ms,
            },
        )
        body = resp.json()
        if not body.get("success"):
            raise RuntimeError(f"Firecrawl error: {body.get('error')}")
        return clean_markdown(body["data"].get("markdown", ""))

    def fetch(self, ref: JobRef) -> RawJob:
        markdown = self.scrape(ref.url)
        return RawJob(ref=ref, content=truncate(markdown, self.settings.max_markdown_chars))

    def normalize(self, raw: RawJob) -> dict:
        title = raw.ref.hints.get("title")
        if not title:
            heading = re.search(r"^#{1,2}\s+(.+)$", raw.content, re.MULTILINE)
            title = heading.group(1) if heading else "Unknown title"
        return {"title": title, "description_text": raw.content}
