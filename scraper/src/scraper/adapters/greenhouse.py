import html as html_lib
import logging
import re
from datetime import date
from itertools import zip_longest

from scraper.adapters.base import SourceAdapter
from scraper.location import location_matches
from scraper.models import EmploymentType, JobRef, RawJob, SearchFilters
from scraper.preprocess import html_to_lines, truncate
from scraper.relevance import min_years_from_items, title_excluded

log = logging.getLogger(__name__)

API = "https://boards-api.greenhouse.io/v1/boards"

# Greenhouse hosts hiring boards for thousands of companies behind one public JSON API
# (documented, no auth). One adapter therefore covers every company in GREENHOUSE_COMPANIES.
# `?content=true` returns each posting's full description in the same single request, so there
# are no per-job fetches. Descriptions come back HTML-escaped.

_RESPONSIBILITIES = re.compile(
    r"responsibilit|what you.ll do|what you will do|the role|your impact|in this role|"
    r"day[- ]to[- ]day|what you.ll be doing",
    re.IGNORECASE,
)
_REQUIRED = re.compile(
    r"qualification|requirement|what we look for|what you.ll bring|what you bring|you.ll have|"
    r"you should have|about you|who you are|minimum|basic|what we.re looking for",
    re.IGNORECASE,
)
_PREFERRED = re.compile(r"preferred|nice to have|bonus|\bpluses\b|\bplus\b", re.IGNORECASE)


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"responsibilities": [], "required": [], "preferred": []}
    current = None
    for line in lines:
        if line.startswith("- "):
            if current:
                sections[current].append(line[2:].strip())
            continue
        if len(line) <= 80:
            if _PREFERRED.search(line):
                current = "preferred"
            elif _REQUIRED.search(line):
                current = "required"
            elif _RESPONSIBILITIES.search(line):
                current = "responsibilities"
            else:
                current = None
    return sections


def _department(job: dict) -> str | None:
    names = [d["name"] for d in job.get("departments") or [] if d.get("name")]
    return ", ".join(names) or None


class GreenhouseAdapter(SourceAdapter):
    name = "greenhouse"
    company = "Greenhouse"

    def extract_external_id(self, url: str) -> str:
        match = re.search(r"gh_jid=(\d+)|/jobs/(\d+)", url)
        if not match:
            raise ValueError(f"Not a Greenhouse job URL: {url}")
        return match.group(1) or match.group(2)

    def discover(self, filters: SearchFilters) -> list[JobRef]:
        per_company: list[list[JobRef]] = []
        for token in self.settings.greenhouse_company_list:
            try:
                jobs = self.client.get_json(f"{API}/{token}/jobs", params={"content": "true"})["jobs"]
            except Exception as exc:
                log.warning("could not load greenhouse board %r: %s", token, exc)
                continue
            refs = [
                JobRef(external_id=str(job["id"]), url=job["absolute_url"], hints={"job": job})
                for job in jobs
                if location_matches((job.get("location") or {}).get("name", ""), filters.locations)
                and not title_excluded(job.get("title") or "")
            ]
            log.info("%s: %d of %d postings match location and title rules", token, len(refs), len(jobs))
            per_company.append(refs)
        # Round-robin so a small --limit still samples every company, not just the first.
        interleaved = [ref for group in zip_longest(*per_company) for ref in group if ref]
        found: dict[str, JobRef] = {}
        for ref in interleaved:
            found.setdefault(ref.external_id, ref)
        return list(found.values())[: filters.limit]

    def fetch(self, ref: JobRef) -> RawJob:
        # The description already arrived with the board listing.
        return RawJob(ref=ref, content="", fields={"job": ref.hints["job"]})

    def normalize(self, raw: RawJob) -> dict:
        job = raw.fields["job"]
        title = job.get("title") or "Unknown title"
        lines = html_to_lines(html_lib.unescape(job.get("content") or ""))
        sections = _split_sections(lines)
        years = min_years_from_items(sections["required"])
        if years is None:
            years = min_years_from_items([line for line in lines if "experience" in line.lower()])
        location = (job.get("location") or {}).get("name", "")
        published = (job.get("first_published") or "")[:10]
        return {
            "title": title.strip(),
            "company": job.get("company_name"),
            "requisition_id": job.get("requisition_id"),
            "employment_type": (
                EmploymentType.internship
                if re.search(r"\bintern(ship)?\b", title, re.IGNORECASE)
                else EmploymentType.unknown
            ),
            "locations": [p.strip() for p in location.split(";") if p.strip()],
            "department": _department(job),
            "posted_date": date.fromisoformat(published) if published else None,
            "min_experience_years": years,
            "overview": "",
            "responsibilities": sections["responsibilities"],
            "required_qualifications": sections["required"],
            "preferred_qualifications": sections["preferred"],
            "description_text": truncate("\n".join(lines), self.settings.max_markdown_chars),
        }
