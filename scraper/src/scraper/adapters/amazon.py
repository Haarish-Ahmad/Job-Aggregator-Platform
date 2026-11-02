import json
import logging
import re
from datetime import date, datetime
from urllib.parse import urlparse

from scraper.adapters.base import SourceAdapter
from scraper.location import location_matches
from scraper.models import EmploymentType, JobRef, RawJob, SearchFilters
from scraper.preprocess import html_to_lines, truncate
from scraper.relevance import title_excluded

log = logging.getLogger(__name__)

BASE = "https://www.amazon.jobs"
SEARCH_URL = f"{BASE}/en/search.json"
_JOB_ID_RE = re.compile(r"/jobs/(\d+)(?:/|$)")
_MAX_PAGE_SIZE = 100


def _posted_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    for date_format in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    return None


def _job_locations(job: dict) -> list[str]:
    locations: list[str] = []
    for entry in job.get("locations") or []:
        if isinstance(entry, str):
            try:
                entry = json.loads(entry)
            except json.JSONDecodeError:
                continue
        if isinstance(entry, dict):
                country = entry.get("normalizedCountryName")
                if not country and entry.get("normalizedCountryCode") in {"IN", "IND"}:
                    country = "India"
                parts = [
                    entry.get("city") or entry.get("normalizedCityName"),
                    entry.get("normalizedStateName"),
                    country,
                ]
                value = ", ".join(part for part in parts if part) or entry.get("normalizedLocation") or entry.get("location")
                if value and value not in locations:
                    locations.append(value)
    if not locations and job.get("normalized_location"):
        locations.append(job["normalized_location"])
    if not locations and job.get("location"):
        locations.append(job["location"])
    return locations


def _qualification_lines(value: str | None) -> list[str]:
    return [line[2:].strip() if line.startswith("- ") else line for line in html_to_lines(value or "")]


class AmazonAdapter(SourceAdapter):
    name = "amazon"
    company = "Amazon"

    def extract_external_id(self, url: str) -> str:
        parsed = urlparse(url)
        match = _JOB_ID_RE.search(parsed.path)
        if parsed.hostname not in {"amazon.jobs", "www.amazon.jobs"} or not match:
            raise ValueError(f"Not an Amazon Jobs URL: {url}")
        return match.group(1)

    def discover(self, filters: SearchFilters) -> list[JobRef]:
        found: dict[str, JobRef] = {}
        queries = filters.queries or [""]
        locations = filters.locations or [""]
        for query in queries:
            for location in locations:
                offset = 0
                while len(found) < filters.limit:
                    # The public endpoint may ignore loc_query, so filter full pages locally.
                    data = self.client.get_json(
                        SEARCH_URL,
                        params={
                            "base_query": query,
                            "loc_query": location,
                            "result_limit": _MAX_PAGE_SIZE,
                            "offset": offset,
                        },
                        headers={"Accept-Encoding": "gzip, deflate"},
                    )
                    jobs = data.get("jobs") or []
                    if not jobs:
                        break
                    for job in jobs:
                        job_locations = _job_locations(job)
                        if filters.locations and not any(
                            location_matches(location, filters.locations) for location in job_locations
                        ):
                            continue
                        job_path = job.get("job_path") or ""
                        url = f"{BASE}{job_path}"
                        try:
                            external_id = self.extract_external_id(url)
                        except ValueError:
                            log.warning("Amazon search result has an invalid job path: %r", job_path)
                            continue
                        title = job.get("title") or ""
                        if external_id in found or title_excluded(title):
                            continue
                        found[external_id] = JobRef(
                            external_id=external_id,
                            url=url,
                            hints={"job": job},
                        )
                        if len(found) >= filters.limit:
                            break
                    offset += len(jobs)
                    if offset >= data.get("hits", 0):
                        break
                if len(found) >= filters.limit:
                    return list(found.values())[: filters.limit]
        return list(found.values())[: filters.limit]

    def fetch(self, ref: JobRef) -> RawJob:
        # Amazon's public search API includes the full posting, so no detail-page request is needed.
        return RawJob(ref=ref, content="", fields={"job": ref.hints["job"]})

    def normalize(self, raw: RawJob) -> dict:
        job = raw.fields["job"]
        title = job.get("title") or "Unknown title"
        overview_lines = html_to_lines(job.get("description_short") or job.get("description") or "")
        description_lines = html_to_lines(job.get("description") or job.get("description_short") or "")
        required = _qualification_lines(job.get("basic_qualifications"))
        preferred = _qualification_lines(job.get("preferred_qualifications"))
        description_text = "\n".join(
            description_lines
            + ["Basic qualifications:"] + [f"- {line}" for line in required]
            + ["Preferred qualifications:"] + [f"- {line}" for line in preferred]
        )
        is_internship = bool(job.get("is_intern")) or bool(re.search(r"\bintern(ship)?\b", title, re.IGNORECASE))
        return {
            "title": title,
            "requisition_id": job.get("id_icims"),
            "employment_type": EmploymentType.internship if is_internship else EmploymentType.unknown,
            "employment_type_raw": job.get("job_schedule_type"),
            "work_mode": None,
            "locations": _job_locations(job),
            "department": job.get("job_category") or job.get("team"),
            "posted_date": _posted_date(job.get("posted_date")),
            "overview": " ".join(overview_lines),
            "responsibilities": [],
            "required_qualifications": required,
            "preferred_qualifications": preferred,
            "description_text": truncate(description_text, self.settings.max_markdown_chars),
        }
