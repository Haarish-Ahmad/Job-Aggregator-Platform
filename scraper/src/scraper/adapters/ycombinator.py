import html as html_lib
import json
import logging
import re

from scraper.adapters.base import SourceAdapter
from scraper.location import location_matches
from scraper.models import EmploymentType, JobRef, RawJob, SearchFilters
from scraper.preprocess import truncate
from scraper.relevance import min_years_from_text, title_excluded, too_experienced

log = logging.getLogger(__name__)

BASE = "https://www.ycombinator.com"
ROLE_PAGE = f"{BASE}/jobs/role/software-engineer"

# YC's job pages are server-rendered (Inertia-style): the whole page's data is a JSON blob in a
# `data-page` attribute. The listing page carries every posting's structured fields; each job's
# own page adds the full description. robots.txt allows /jobs and /companies/<slug>/jobs/*.
# PoliteClient defaults to Accept: application/json, which YC answers with a 404 for page URLs.
_HTML = {"Accept": "text/html"}
_DATA_PAGE_RE = re.compile(r'data-page="([^"]+)"')

_EMPLOYMENT = {
    "internship": EmploymentType.internship,
    "full-time": EmploymentType.full_time,
    "part-time": EmploymentType.part_time,
    "contract": EmploymentType.contract,
}


def _page_props(page_html: str) -> dict:
    match = _DATA_PAGE_RE.search(page_html)
    if not match:
        raise ValueError("no data-page JSON found in YC page")
    return json.loads(html_lib.unescape(match.group(1)))["props"]


def _years_from_label(label: str | None) -> int | None:
    """'3+ years' -> 3, 'Any (new grads ok)' -> 0, missing -> None."""
    if not label:
        return None
    if label.lower().startswith("any"):
        return 0
    return min_years_from_text(label)


class YCombinatorAdapter(SourceAdapter):
    name = "ycombinator"
    company = "Y Combinator"

    def extract_external_id(self, url: str) -> str:
        match = re.search(r"/companies/[^/]+/jobs/([A-Za-z0-9]+)", url)
        if not match:
            raise ValueError(f"Not a YC job URL: {url}")
        return match.group(1)

    def discover(self, filters: SearchFilters) -> list[JobRef]:
        found: dict[str, JobRef] = {}
        # The role page is fixed to software engineering; queries don't apply to it.
        # Location pages are slugs like /india, /new-york (see the sidebar on the site).
        slugs = [re.sub(r"[^a-z0-9]+", "-", loc.lower()).strip("-") for loc in filters.locations]
        # The global page is always loaded too: location pages miss some local roles (Bengaluru
        # jobs only appear on the global page), and every posting is location-checked anyway.
        pages = [ROLE_PAGE] + [f"{ROLE_PAGE}/{slug}" for slug in dict.fromkeys(slugs) if slug]
        for page_url in pages:
            if len(found) >= filters.limit:
                break
            self._load_page(page_url, filters, found)
        return list(found.values())[: filters.limit]

    def _load_page(self, page_url: str, filters: SearchFilters, found: dict[str, JobRef]) -> None:
        try:
            postings = _page_props(self.client.request("GET", page_url, headers=_HTML).text)["jobPostings"]
        except Exception as exc:
            log.warning("could not load %s: %s", page_url, exc)
            return
        for job in postings:
            if len(found) >= filters.limit:
                return
            external_id = str(job["id"])
            title = job.get("title") or ""
            is_internship = job.get("type") == "Internship"
            if external_id in found or job.get("role") != "eng" or title_excluded(title):
                continue
            if not location_matches(job.get("location") or "", filters.locations):
                continue
            if too_experienced(title, is_internship, _years_from_label(job.get("minExperience"))):
                continue
            found[external_id] = JobRef(
                external_id=external_id,
                url=f"{BASE}{job['url']}",
                hints={"job": job},
            )

    def fetch(self, ref: JobRef) -> RawJob:
        detail = _page_props(self.client.request("GET", ref.url, headers=_HTML).text)["job"]
        return RawJob(ref=ref, content=detail.get("description") or "", fields={"job": detail})

    def normalize(self, raw: RawJob) -> dict:
        job = raw.fields["job"]
        listing = raw.ref.hints.get("job", {})
        employment_type = _EMPLOYMENT.get((job.get("type") or "").lower(), EmploymentType.unknown)
        location = job.get("location") or ""
        description = truncate(raw.content.strip(), self.settings.max_markdown_chars)
        overview_parts = [job.get("companyOneLiner") or ""]
        if job.get("salaryRange"):
            overview_parts.append(f"Salary: {job['salaryRange']}")
        return {
            "title": job.get("title") or listing.get("title") or "Unknown title",
            "company": job.get("companyName"),
            "employment_type": employment_type,
            "employment_type_raw": job.get("type"),
            "work_mode": None,
            "locations": [part.strip() for part in location.split(" / ") if part.strip()],
            "department": job.get("prettyRole"),
            "posted_date": None,  # YC only gives relative text like "over 3 years"
            "min_experience_years": _years_from_label(job.get("minExperience")),
            "overview": " ".join(part for part in overview_parts if part),
            "responsibilities": [],
            "required_qualifications": list(job.get("skills") or []),
            "preferred_qualifications": [],
            "description_text": description,
        }
