import logging
import re
from datetime import UTC, date, datetime

from scraper.adapters.base import SourceAdapter
from scraper.models import JobRef, RawJob, SearchFilters
from scraper.preprocess import html_to_lines
from scraper.relevance import title_excluded

log = logging.getLogger(__name__)

BASE = "https://www.google.com/about/careers/applications"

# Google Careers' search-results page is server-rendered: job data (title, full HTML
# description, company, locations, timestamps) is embedded directly in a JS data blob
# (`AF_initDataCallback({key: 'ds:1', ..., data: [...]})`). No detail-page fetch needed.
#
# robots.txt disallows any URL containing a `page=` param (for generic crawlers; the
# broader block on the whole /jobs/results path is Yandex-only). That means we cannot
# paginate past the first 20 results of any one query. We cover more ground the same way
# a real visitor would: by varying the `q=` keyword across calls, same dedup pattern as
# the Microsoft adapter.
_DATA_BLOCK_RE = re.compile(r"AF_initDataCallback\((\{.*?\})\);", re.S)
_CANONICAL_URL_RE = re.compile(r'jobs/results/(\d+)-([^"&?\\\s]+)')


def _parse_ds1(html: str) -> list[list] | None:
    for raw in _DATA_BLOCK_RE.findall(html):
        if "key: 'ds:1'" not in raw and 'key:"ds:1"' not in raw:
            continue
        match = re.search(r"data:\s*(\[.*\])\s*,\s*sideChannel", raw, re.S)
        if not match:
            continue
        import json

        # Zero-result queries come back as data:[null,null,0,20] (no jobs array at all).
        return json.loads(match.group(1))[0] or []
    return None


def _canonical_urls(html: str) -> dict[str, str]:
    return {job_id: f"{BASE}/jobs/results/{job_id}-{slug}" for job_id, slug in _CANONICAL_URL_RE.findall(html)}


def _html_field(job: list, index: int) -> str:
    value = job[index] if index < len(job) else None
    if not value or not isinstance(value, list) or len(value) < 2 or not value[1]:
        return ""
    return value[1]


def _split_qualifications(html: str) -> tuple[list[str], list[str]]:
    """Google's qualifications field has both sections in one HTML blob,
    separated by '<h3>Minimum qualifications:</h3>' / '<h3>Preferred qualifications:</h3>'."""
    required, preferred = [], []
    current = required
    for line in html_to_lines(html):
        lowered = line.lower().strip(" :")
        if lowered == "minimum qualifications":
            current = required
            continue
        if lowered == "preferred qualifications":
            current = preferred
            continue
        if line.startswith("- "):
            current.append(line[2:].strip())
    return required, preferred


def _posted_date(job: list) -> date | None:
    ts = job[12] if len(job) > 12 else None
    if not ts or not isinstance(ts, list) or not ts[0]:
        return None
    return datetime.fromtimestamp(ts[0], UTC).date()


class GoogleAdapter(SourceAdapter):
    name = "google"
    company = "Google"

    def extract_external_id(self, url: str) -> str:
        match = re.search(r"/jobs/results/(\d+)-", url)
        if not match:
            raise ValueError(f"Not a Google Careers job URL: {url}")
        return match.group(1)

    def discover(self, filters: SearchFilters) -> list[JobRef]:
        found: dict[str, JobRef] = {}
        for query in filters.queries:
            if len(found) >= filters.limit:
                break
            for location in filters.locations or [""]:
                if len(found) >= filters.limit:
                    break
                self._search(query, location, filters.limit, found)
        return list(found.values())[: filters.limit]

    def _search(self, query: str, location: str, limit: int, found: dict[str, JobRef]) -> None:
        params = {}
        if query:
            params["q"] = query
        if location:
            params["location"] = location
        resp = self.client.request("GET", f"{BASE}/jobs/results", params=params)
        html = resp.text
        jobs = _parse_ds1(html)
        if jobs is None:
            log.warning("could not parse search results for query=%r location=%r", query, location)
            return
        if not jobs:
            log.info("zero results for query=%r location=%r", query, location)
            return
        urls = _canonical_urls(html)
        for job in jobs:
            if len(found) >= limit:
                return
            external_id = str(job[0])
            title = job[1] if len(job) > 1 else "Unknown title"
            if external_id in found or title_excluded(title):
                continue
            url = urls.get(external_id, f"{BASE}/jobs/results/{external_id}")
            found[external_id] = JobRef(external_id=external_id, url=url, hints={"job": job})

    def fetch(self, ref: JobRef) -> RawJob:
        # Everything we need was already embedded in the search-results page from discover().
        return RawJob(ref=ref, content="", fields={"job": ref.hints["job"]})

    def normalize(self, raw: RawJob) -> dict:
        job = raw.fields["job"]
        title = job[1] if len(job) > 1 else raw.ref.hints.get("title", "Unknown title")
        company = job[7] if len(job) > 7 and job[7] else self.company
        locations = [entry[0] for entry in (job[9] if len(job) > 9 and job[9] else []) if entry]
        overview_lines = html_to_lines(_html_field(job, 10))
        responsibilities = [
            line[2:].strip() for line in html_to_lines(_html_field(job, 3)) if line.startswith("- ")
        ]
        required, preferred = _split_qualifications(_html_field(job, 4))
        employment_type = "internship" if re.search(r"\bintern\b", title, re.IGNORECASE) else "unknown"
        description_text = "\n".join(
            overview_lines + ["Responsibilities:"] + [f"- {r}" for r in responsibilities]
            + ["Minimum qualifications:"] + [f"- {r}" for r in required]
            + ["Preferred qualifications:"] + [f"- {r}" for r in preferred]
        )
        return {
            "title": title,
            "company": company,  # "Google" or a sub-brand such as "YouTube"
            "employment_type": employment_type,
            "employment_type_raw": str(job[20]) if len(job) > 20 else None,
            "work_mode": None,  # not reliably present per-job in this data block
            "locations": locations,
            "department": None,
            "posted_date": _posted_date(job),
            "overview": " ".join(overview_lines),
            "responsibilities": responsibilities,
            "required_qualifications": required,
            "preferred_qualifications": preferred,
            "description_text": description_text,
        }
