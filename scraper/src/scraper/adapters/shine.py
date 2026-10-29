import logging
import re

from scraper.adapters.firecrawl_base import FirecrawlAdapter
from scraper.models import EmploymentType, JobRef, RawJob, SearchFilters, WorkMode
from scraper.relevance import title_excluded, too_experienced

log = logging.getLogger(__name__)

BASE = "https://www.shine.com"
MAX_PAGES = 5  # 20 postings per page; deep pages are mostly stale

# Shine's search pages and job pages are Next.js apps: the postings only exist after the page's
# JavaScript has run, so Firecrawl renders them to markdown. Search URLs are
# /job-search/<query-slug>-jobs[-in-<city>][-<page>]; a ?page= parameter is ignored by the site.
# robots.txt allows /job-search/ and job pages (the PoliteClient also applies its /jobs/1*, /jobs/9* rules).

_CITY_SLUGS = {"bengaluru": "bangalore", "gurugram": "gurgaon", "mumbai": "mumbai", "new delhi": "delhi"}

_CARD_RE = re.compile(
    r"###\s*\[(?P<title>[^\]]+)\]\((?P<url>https://www\.shine\.com/jobs/[^)\s]+)\)\s*\n+"
    r"(?P<meta>[^\n]+)\n*(?:Required:(?P<skills>[^\n]*))?"
)
_AGO_RE = re.compile(r"\s*(?:\d+\s+(?:minute|hour|day|week|month|year)s?\s+ago|just now|today)\s*$", re.IGNORECASE)
# Promotional labels Shine puts between the employer line and the title ("Actively Hiring", "Be An Early Applicant"...).
_BADGE_RE = re.compile(r"^(?:actively hiring|be an early applicant|early applicant|urgent(?:ly)? hiring|featured|premium|verified|new)+$",
                       re.IGNORECASE)
_EXPERIENCE_RE = re.compile(r"^(\d{1,2})(?:\s*to\s*\d{1,2})?\s*Yrs?", re.IGNORECASE)
_DESCRIPTION_RE = re.compile(r"Job Description\n-+\n(.*?)(?:\nIndustry\n|\nRead full description|\Z)", re.DOTALL)
_SKILL_RE = re.compile(r"\[([^\]]+)\]\(https://www\.shine\.com/job-search/")

_EMPLOYMENT = {
    "full time": EmploymentType.full_time,
    "part time": EmploymentType.part_time,
    "internship": EmploymentType.internship,
    "contract": EmploymentType.contract,
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def search_urls(query: str, location: str, page: int) -> str:
    """Shine search URL for a query, an Indian city (or 'India' for all of India) and a page number."""
    path = f"{_slug(query)}-jobs"
    if location and location.lower() != "india":
        path += f"-in-{_CITY_SLUGS.get(location.lower(), _slug(location))}"
    if page > 1:
        path += f"-{page}"
    return f"{BASE}/job-search/{path}"


def _company_from(lines_before_title: list[str]) -> str:
    """The employer is the line that ends with the posting age ('Acme Ltd1 week ago'), a few lines above the title.
    Promotional badge lines can sit between that line and the title, so the last line is not always the employer."""
    recent = lines_before_title[-5:]
    for line in reversed(recent):
        if _AGO_RE.search(line):
            return _AGO_RE.sub("", line).strip()
    for line in reversed(recent):  # no age line (layout change): the nearest line that is not a badge
        if not _BADGE_RE.match(line.replace(" ", "")) and not _BADGE_RE.match(line):
            return line.strip()
    return ""


def parse_listing(markdown: str) -> list[dict]:
    """Search-results markdown -> one dict per posting card (url, title, company, years, skills)."""
    cards = []
    for match in _CARD_RE.finditer(markdown):
        before = [ln.strip() for ln in markdown[: match.start()].splitlines() if ln.strip() and not ln.startswith("![")]
        company = _company_from(before)
        years = _EXPERIENCE_RE.match(match.group("meta").strip())
        cards.append(
            {
                "title": match.group("title").strip(),
                "url": match.group("url").split("?")[0],
                "company": company,
                "min_years": int(years.group(1)) if years else None,
                "skills": [s.strip() for s in (match.group("skills") or "").split("·") if s.strip()],
            }
        )
    return cards


def _line_value(markdown: str, label: str) -> str:
    """Value of a header line like 'Experience0 to 4 Yrs' (label and value are run together)."""
    match = re.search(rf"^{label}(.+)$", markdown, re.MULTILINE)
    return match.group(1).strip() if match else ""


class ShineAdapter(FirecrawlAdapter):
    name = "shine"
    india_portal = True
    company = "Shine"
    default_queries = [
        "software developer fresher",
        "full stack developer fresher",
        "machine learning fresher",
        "artificial intelligence fresher",
        "data scientist fresher",
        "data analyst fresher",
        "data engineer fresher",
        "cyber security fresher",
        "devops cloud engineer fresher",
        "python developer fresher",
        "java developer fresher",
        "software developer intern",
        "machine learning intern",
        "cyber security intern",
    ]

    def extract_external_id(self, url: str) -> str:
        match = re.search(r"/jobs/[^/]+/[^/]+/(\d+)", url)
        if not match:
            raise ValueError(f"Not a Shine job URL: {url}")
        return match.group(1)

    def discover(self, filters: SearchFilters) -> list[JobRef]:
        found: dict[str, JobRef] = {}
        pairs = [(q, loc) for q in filters.queries for loc in (filters.locations or ["India"])]
        # Each query gets a fair share of the limit so the first queries (software) don't use it all up;
        # a second pass hands any unused share to whatever still has postings.
        share = -(-filters.limit // len(pairs))
        for per_pair_cap in (share, filters.limit):
            for query, location in pairs:
                if len(found) >= filters.limit:
                    return list(found.values())
                cap = filters.limit if per_pair_cap == filters.limit else len(found) + share
                self._search(query, location, min(cap, filters.limit), found)
        return list(found.values())

    def _search(self, query: str, location: str, limit: int, found: dict[str, JobRef]) -> None:
        for page in range(1, MAX_PAGES + 1):
            url = search_urls(query, location, page)
            try:
                cards = parse_listing(self.scrape(url))
            except Exception as exc:
                log.warning("could not load %s: %s", url, exc)
                return
            fresh = 0
            for card in cards:
                try:
                    external_id = self.extract_external_id(card["url"])
                except ValueError:
                    continue
                if external_id in found:
                    continue
                fresh += 1
                if title_excluded(card["title"]) or too_experienced(card["title"], False, card["min_years"]):
                    continue
                found[external_id] = JobRef(external_id=external_id, url=card["url"], hints=card)
                if len(found) >= limit:
                    return
            if not fresh:
                return  # page repeated what we already had: past the last page

    def normalize(self, raw: RawJob) -> dict:
        md, hints = raw.content, raw.ref.hints
        location_text = _line_value(md, "Location")
        locations = [p.strip() for p in re.findall(r"\[([^\]]+)\]", location_text)] or (
            [location_text] if location_text else []
        )
        skills_block = md.split("Skills For This Role", 1)[-1].split("Job Description", 1)[0]
        skills = _SKILL_RE.findall(skills_block) or list(hints.get("skills") or [])
        description = _DESCRIPTION_RE.search(md)
        employment_raw = _line_value(md, "Type")
        salary = _line_value(md, "Salary")
        experience = _EXPERIENCE_RE.match(_line_value(md, "Experience"))
        years = int(experience.group(1)) if experience else None
        title = hints.get("title") or "Unknown title"
        company = hints.get("company") or (re.search(r"Posted By\*\*(.+?)\*\*", md) or [None, ""])[1]
        return {
            "title": title,
            "company": company or None,
            "employment_type": _EMPLOYMENT.get(employment_raw.lower(), EmploymentType.unknown),
            "employment_type_raw": employment_raw or None,
            "work_mode": WorkMode.remote if re.search(r"\bWFH\b|work from home", title, re.IGNORECASE) else None,
            "locations": locations,
            "posted_date": None,  # Shine only gives relative text like "1 month ago"
            "min_experience_years": years if years is not None else hints.get("min_years"),
            "overview": f"Salary: {salary}" if salary and salary.lower() != "not disclosed" else "",
            "required_qualifications": skills,
            "description_text": (description.group(1) if description else md).strip(),
        }
