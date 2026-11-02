import logging
import re
from datetime import date

from scraper.adapters.base import SourceAdapter
from scraper.location import location_matches
from scraper.models import EmploymentType, JobRef, RawJob, SearchFilters, WorkMode
from scraper.preprocess import html_to_lines, truncate
from scraper.relevance import title_excluded

log = logging.getLogger(__name__)

SITE = "https://unstop.com"
API = f"{SITE}/api/public/opportunity/search-result"

# Unstop is an Indian student platform. Its pages are a JS app, but the app reads this public JSON
# endpoint (robots.txt: the longer `Allow: /api/public/*` beats `Disallow: /api/*`). Each result
# already carries the full HTML description, so there is no per-job request.
#
# Postings declare who may apply ("Fresher", "Experienced Professionals", ...). That list is our
# entry-level signal: postings usually have no experience number.
_STUDENT_ELIGIBLE = {"Fresher", "Undergraduate", "Engineering Students", "All"}
_OPPORTUNITIES = ("jobs", "internships")
_PER_PAGE = 50

# Unstop tags every posting with work functions ("Software Development", "Network Administration"...).
# That is far more reliable than guessing from the title, so a posting must have a software one.
_SOFTWARE_FUNCTION = re.compile(
    r"software|(front|back)[- ]?end|full[- ]?stack|\bweb\b|android|\bios\b|mobile app|\bapi\b|devops|"
    r"cloud|platform engineering|systems programming|data (science|engineering|analy)|machine learning|"
    r"\bai\b|\bnlp\b|agentic|embedded|testing|\bqa\b|quality assurance|cyber|security engineering|"
    r"forward deployed|sdet|site reliability|programming",
    re.IGNORECASE,
)

_TIMING = {
    "full_time": EmploymentType.full_time,
    "part_time": EmploymentType.part_time,
    "contractual": EmploymentType.contract,
    "contract": EmploymentType.contract,
}
_WORK_MODE = {
    "in_office": WorkMode.onsite,
    "on_field": WorkMode.onsite,
    "hybrid": WorkMode.hybrid,
    "wfh": WorkMode.remote,
}
_CURRENCY = {"fa-rupee": "₹", "fa-dollar": "$", "fa-euro": "€", "fa-pound": "£"}


def _eligible(job: dict) -> set[str]:
    return {f["name"] for f in job.get("filters") or [] if f.get("type") == "eligible"}


def _is_software_function(job: dict) -> bool:
    names = [w.get("name") or "" for w in job.get("workfunction") or []]
    return not names or any(_SOFTWARE_FUNCTION.search(n) for n in names)


def _place_strings(job: dict) -> list[str]:
    return [
        ", ".join(part for part in (loc.get("city"), loc.get("state"), loc.get("country")) if part)
        for loc in job.get("locations") or []
    ]


def _location_ok(job: dict, wanted: list[str]) -> bool:
    places = _place_strings(job)
    # Work-from-home postings list no place; Unstop only serves India, so keep them.
    return not places or any(location_matches(p, wanted) for p in places)


def _salary_text(detail: dict) -> str | None:
    low, high = detail.get("min_salary"), detail.get("max_salary")
    if not detail.get("show_salary") or not (low or high):
        return None
    symbol = _CURRENCY.get(detail.get("currency") or "", "")
    amount = f"{symbol}{low:,}" if low == high or not high else f"{symbol}{low:,}-{symbol}{high:,}"
    return f"Salary: {amount} {detail.get('pay_in') or ''}".strip()


def _approved_date(job: dict) -> date | None:
    try:
        return date.fromisoformat((job.get("approved_date") or "")[:10])
    except ValueError:
        return None


class UnstopAdapter(SourceAdapter):
    name = "unstop"
    india_portal = True
    company = "Unstop"
    default_queries = [
        "software", "developer", "engineer", "sde", "data", "machine learning",
        "web", "full stack", "testing", "cyber", "devops", "python", "java",
    ]

    def extract_external_id(self, url: str) -> str:
        match = re.search(r"-(\d+)/?(?:\?|$)", url)
        if not match:
            raise ValueError(f"Not an Unstop opportunity URL: {url}")
        return match.group(1)

    def discover(self, filters: SearchFilters) -> list[JobRef]:
        found: dict[str, JobRef] = {}
        for opportunity in _OPPORTUNITIES:
            for query in filters.queries:
                if len(found) >= filters.limit:
                    return list(found.values())
                self._search(opportunity, query, filters, found)
        return list(found.values())

    def _search(self, opportunity: str, query: str, filters: SearchFilters, found: dict[str, JobRef]) -> None:
        page = 1
        while len(found) < filters.limit:
            params = {"opportunity": opportunity, "oppstatus": "open", "per_page": _PER_PAGE, "page": page}
            if query:
                params["searchTerm"] = query
            data = self.client.get_json(API, params=params)["data"]
            for job in data.get("data", []):
                external_id = str(job["id"])
                if external_id in found or title_excluded(job.get("title") or ""):
                    continue
                if not _eligible(job) & _STUDENT_ELIGIBLE or not _is_software_function(job):
                    continue
                if not _location_ok(job, filters.locations):
                    continue
                found[external_id] = JobRef(
                    external_id=external_id,
                    url=job.get("seo_url") or f"{SITE}/{job['public_url']}",
                    hints={"job": job},
                )
                if len(found) >= filters.limit:
                    return
            if page >= data.get("last_page", 1):
                return
            page += 1

    def fetch(self, ref: JobRef) -> RawJob:
        return RawJob(ref=ref, content="", fields={"job": ref.hints["job"]})

    def normalize(self, raw: RawJob) -> dict:
        job = raw.fields["job"]
        detail = job.get("jobDetail") or {}
        eligible = sorted(_eligible(job))
        skills = [s["skill_name"] for s in job.get("required_skills") or [] if s.get("skill_name")]
        lines = html_to_lines(job.get("details") or "")
        extra = [line for line in (_salary_text(detail), f"Eligibility: {', '.join(eligible)}" if eligible else None,
                                   f"Skills: {', '.join(skills)}" if skills else None) if line]
        title = (job.get("title") or "Unknown title").strip()
        # Some "jobs" are titled "...Internship"; the title is the more honest label.
        is_internship = job.get("subtype") == "internships" or bool(re.search(r"\bintern(ship)?\b", title, re.I))
        timing = detail.get("timing")
        locations = [p for p in _place_strings(job) if p] or (["Work from home"] if detail.get("type") == "wfh" else [])
        min_experience = detail.get("min_experience")
        if min_experience is None and set(eligible) & _STUDENT_ELIGIBLE:
            min_experience = 0  # open to freshers
        return {
            "title": title,
            "company": (job.get("organisation") or {}).get("name"),
            "employment_type": EmploymentType.internship if is_internship else _TIMING.get(timing, EmploymentType.unknown),
            "employment_type_raw": timing,
            "work_mode": _WORK_MODE.get(detail.get("type") or ""),
            "locations": locations,
            "department": ", ".join(w["name"] for w in job.get("workfunction") or [] if w.get("name")) or None,
            "posted_date": _approved_date(job),
            "min_experience_years": min_experience,
            "overview": " ".join(extra[:2]),
            "responsibilities": [],
            "required_qualifications": skills,
            "preferred_qualifications": [],
            "description_text": truncate("\n".join(lines + extra), self.settings.max_markdown_chars),
        }
