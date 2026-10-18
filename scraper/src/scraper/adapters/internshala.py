import logging
import re
from datetime import UTC, datetime, timedelta

from bs4 import BeautifulSoup

from scraper.adapters.base import SourceAdapter
from scraper.models import JobRef, RawJob, SearchFilters

log = logging.getLogger(__name__)

BASE = "https://internshala.com"

# Only software-related categories: the generic /internships/ and /jobs/ lists mix in marketing, design, etc.
CATEGORY_PATHS = {
    "computer-science": "/internships/computer-science-internship/",
    # Internshala renamed these two; the old slugs now 301 to the generic /internships/ list.
    "software-engineering": "/internships/software-development-internship/",
    "data-science": "/internships/data-science-internship/",
    "ai-ml": "/internships/artificial-intelligence-ai-internship/",
    "machine-learning": "/internships/machine-learning-internship/",
    "cyber-security": "/internships/cyber-security-internship/",
}

# Relative time strings on cards ("6 days ago") → timedelta
RELATIVE_TIME = {
    r"(\d+)\s+days?\s+ago": lambda m: timedelta(days=int(m.group(1))),
    r"(\d+)\s+hours?\s+ago": lambda m: timedelta(hours=int(m.group(1))),
    r"(\d+)\s+weeks?\s+ago": lambda m: timedelta(weeks=int(m.group(1))),
    r"(\d+)\s+months?\s+ago": lambda m: timedelta(days=int(m.group(1)) * 30),
    r"just\s+(?:now|posted)": lambda m: timedelta(0),
}


def parse_relative_time(text: str) -> str | None:
    """'6 days ago' → ISO date string, or None if unparseable."""
    for pattern, delta_fn in RELATIVE_TIME.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            dt = datetime.now(UTC) - delta_fn(m)
            return dt.date().isoformat()
    return None


def parse_stipend(text: str) -> dict:
    """'₹ 10,000 - 12,000 /month' → {'min': 10000, 'max': 12000, 'currency': 'INR', 'period': 'month'}."""
    result = {"min": None, "max": None, "currency": None, "period": None}
    currency_map = {"₹": "INR", "$": "USD", "€": "EUR"}
    for curr_symbol, curr_code in currency_map.items():
        if curr_symbol in text:
            result["currency"] = curr_code
            break
    numbers = re.findall(r"(\d+(?:,\d+)*)", text)
    if len(numbers) >= 2:
        result["min"] = int(numbers[0].replace(",", ""))
        result["max"] = int(numbers[1].replace(",", ""))
    elif len(numbers) == 1:
        result["min"] = int(numbers[0].replace(",", ""))
    for period in ["month", "week", "day", "year"]:
        if period in text.lower():
            result["period"] = period
            break
    return result


class InternshalaAdapter(SourceAdapter):
    name = "internshala"
    company = "Internshala"
    software_trusted = True  # every category above is a software category
    india_portal = True
    default_queries = ["computer-science", "software-engineering", "data-science", "ai-ml", "machine-learning", "cyber-security"]

    def extract_external_id(self, url: str) -> str:
        # URL is /internship/detail/slug-internshipid; extract the ID at the end.
        match = re.search(r"internship_id=(\d+)", url)
        if match:
            return match.group(1)
        match = re.search(r"(\d+)/?$", url)
        if match:
            return match.group(1)
        raise ValueError(f"Not an Internshala URL: {url}")

    def discover(self, filters: SearchFilters) -> list[JobRef]:
        found: dict[str, JobRef] = {}
        # Map each query to its Internshala category URL (unknown ones fall back to computer-science).
        paths = [CATEGORY_PATHS.get(q.lower(), CATEGORY_PATHS["computer-science"]) for q in filters.queries]
        paths = list(dict.fromkeys(paths))
        # Fair share per category so the first one doesn't fill the limit; a second pass uses leftovers.
        share = -(-filters.limit // len(paths))
        for second_pass in (False, True):
            for path in paths:
                if len(found) >= filters.limit:
                    return list(found.values())
                cap = filters.limit if second_pass else min(filters.limit, len(found) + share)
                self._search_category(path, cap, found)
        return list(found.values())[: filters.limit]

    def _search_category(self, category_path: str, limit: int, found: dict[str, JobRef]) -> None:
        page = 1
        max_pages = 1
        while page <= max_pages and len(found) < limit:
            if page == 1:
                url = f"{BASE}{category_path}"
            else:
                url = f"{BASE}{category_path}page-{page}/"
            try:
                resp = self.client.request("GET", url, headers={"Referer": f"{BASE}/"})
                if not resp.url.path.startswith(category_path):
                    # A renamed category redirects to the all-categories list: stop rather than read it.
                    log.warning("%s redirected to %s; category slug needs updating", url, resp.url)
                    break
                html = resp.text
                soup = BeautifulSoup(html, "html.parser")
                # Extract max pages from pagination links
                page_links = soup.select("#pagination a")
                if page_links:
                    numbers = []
                    for link in page_links:
                        text = link.get_text(strip=True)
                        if text.isdigit():
                            numbers.append(int(text))
                    if numbers:
                        max_pages = max(numbers)
                # Parse cards
                for card in soup.select("div.individual_internship"):
                    if len(found) >= limit:
                        break
                    external_id = card.get("internshipid")
                    if not external_id or external_id in found:
                        continue
                    detail_href = card.get("data-href") or card.select_one("a[href*='/internship/detail']")
                    if detail_href and isinstance(detail_href, str):
                        detail_url = detail_href
                    elif detail_href:
                        detail_url = detail_href.get("href")
                    else:
                        continue
                    if not detail_url.startswith("http"):
                        detail_url = f"{BASE}{detail_url}"
                    title = card.select_one(".job-internship-name, .internship-name")
                    title = title.get_text(strip=True) if title else "Unknown"
                    found[external_id] = JobRef(
                        external_id=external_id,
                        url=detail_url,
                        hints={"title": title, "html": str(card)},
                    )
            except Exception as exc:
                log.error("error scraping %s page %d: %s", category_path, page, exc)
                break
            page += 1

    def fetch(self, ref: JobRef) -> RawJob:
        # We already have the card HTML in hints from discover().
        # We don't fetch detail pages (robots.txt blocks /internship/details/).
        return RawJob(ref=ref, content=ref.hints.get("html", ""), fields={"from_listing": True})

    def normalize(self, raw: RawJob) -> dict:
        soup = BeautifulSoup(raw.content, "html.parser")
        card = soup.find("div", class_="individual_internship")
        if not card:
            card = soup
        title = raw.ref.hints.get("title", "Unknown")
        company_el = card.select_one(".company-name")
        # None (not "Unknown") when absent, so build_record falls back to the source name.
        company = company_el.get_text(strip=True) if company_el else None
        location_elem = card.select_one(".locations")
        location = [location_elem.get_text(strip=True)] if location_elem else []
        is_actively_hiring = "Actively" in card.get_text()
        stipend_elem = card.select_one(".stipend, .salary")
        stipend_text = stipend_elem.get_text(strip=True) if stipend_elem else ""
        # Duration is usually a short phrase like "6 Months" or "2 Weeks"
        duration = None
        for text in card.get_text("\n").split("\n"):
            text = text.strip()
            if any(unit in text for unit in ["Months", "Weeks", "Days", "months", "weeks", "days"]):
                if len(text) < 50:
                    duration = text
                    break
        # Find the posted date (last line is usually the time posted)
        posted_lines = [
            line.strip()
            for line in card.get_text("\n").split("\n")
            if "ago" in line.lower() or "posted" in line.lower()
        ]
        posted_date = parse_relative_time(posted_lines[0]) if posted_lines else None
        # Skills are in .job_skill elements or .job_skills container
        skills = []
        for skill_elem in card.select(".job_skill"):
            skill = skill_elem.get_text(strip=True)
            if skill and len(skill) < 50 and skill != "+2 more":
                skills.append(skill)
        # Description snippet is in .about_job > p.text
        description_elem = card.select_one(".about_job .text, .description, .internship-snippet")
        description = description_elem.get_text(strip=True) if description_elem else ""
        return {
            "title": title,
            "company": company,
            "description_text": description,
            "locations": location,
            "work_mode": None,
            "employment_type": "internship",
            "responsibilities": [f"Duration: {duration}"] if duration else [],
            "required_qualifications": skills,
            "preferred_qualifications": [],
            "department": None,
            "posted_date": posted_date,
            "overview": f"Active: {is_actively_hiring}. Stipend: {stipend_text}",
        }
