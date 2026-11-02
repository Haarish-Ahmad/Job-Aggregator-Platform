import logging
import re
from datetime import UTC, datetime

from scraper.adapters.base import SourceAdapter
from scraper.models import EmploymentType, JobRef, RawJob, SearchFilters, WorkMode
from scraper.preprocess import html_to_lines
from scraper.relevance import title_excluded

log = logging.getLogger(__name__)

BASE = "https://apply.careers.microsoft.com"
DOMAIN = "microsoft.com"

# Microsoft's careers site is an Eightfold SPA. Rather than scrape the rendered page
# (which is ~490K chars of embedded JSON config around ~3K chars of real text), we call the
# same public JSON API the page itself uses. robots.txt explicitly allows /api/pcsx.

_EMPLOYMENT = {
    "internship": EmploymentType.internship,
    "intern": EmploymentType.internship,
    "full-time": EmploymentType.full_time,
    "full time": EmploymentType.full_time,
    "part-time": EmploymentType.part_time,
    "part time": EmploymentType.part_time,
    "contract": EmploymentType.contract,
    "contractor": EmploymentType.contract,
}
_WORK_MODE = {"onsite": WorkMode.onsite, "hybrid": WorkMode.hybrid, "remote": WorkMode.remote}

# Boilerplate paragraphs that end a qualifications/responsibilities list.
_BOILERPLATE_STARTS = (
    "microsoft is an equal opportunity",
    "this position will be open",
    "benefits/perks listed",
    "#",
)


def _heading_key(line: str) -> str | None:
    """Map a line to a section name if it is a section heading, else None."""
    if line.startswith("- ") or len(line) > 60:
        return None
    norm = line.lower().strip(" :*")
    if norm == "overview":
        return "overview"
    if norm in ("responsibilities", "key responsibilities"):
        return "responsibilities"
    if norm == "qualifications":
        return "required"  # a bare "Qualifications" heading precedes the Required list
    if "preferred" in norm and "qualification" in norm:
        return "preferred"
    if ("required" in norm or "minimum" in norm or "basic" in norm) and "qualification" in norm:
        return "required"
    if norm in ("other qualifications", "other requirements", "benefits"):
        return "other"
    return None


def parse_sections(lines: list[str]) -> dict:
    sections: dict[str, list[str]] = {
        k: [] for k in ("overview", "responsibilities", "required", "preferred", "other")
    }
    current = None
    for line in lines:
        key = _heading_key(line)
        if key:
            current = key
            continue
        if line.lower().startswith(_BOILERPLATE_STARTS):
            current = "other"
        if current:
            sections[current].append(line)

    def items(name: str) -> list[str]:
        raw = sections[name]
        bullets = [line[2:].strip() for line in raw if line.startswith("- ")]
        # Some postings write requirements as paragraphs instead of bullets.
        return bullets or [line for line in raw if not line.startswith("- ")]

    return {
        "overview": " ".join(line for line in sections["overview"] if not line.startswith("- ")),
        "responsibilities": items("responsibilities"),
        "required_qualifications": items("required"),
        "preferred_qualifications": items("preferred"),
    }


def _first(value) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value) if value else None


def _employment_type(fields: dict, title: str) -> tuple[EmploymentType, str | None]:
    raw = _first(fields.get("efcustomTextEmploymentType"))
    if raw and raw.lower().strip() in _EMPLOYMENT:
        return _EMPLOYMENT[raw.lower().strip()], raw
    if re.search(r"\bintern(ship)?\b", title, re.IGNORECASE):
        return EmploymentType.internship, raw
    return EmploymentType.unknown, raw


class MicrosoftAdapter(SourceAdapter):
    name = "microsoft"
    company = "Microsoft"

    def extract_external_id(self, url: str) -> str:
        match = re.search(r"/careers/job/(\d+)", url)
        if not match:
            raise ValueError(f"Not a Microsoft job URL: {url}")
        return match.group(1)

    def discover(self, filters: SearchFilters) -> list[JobRef]:
        found: dict[str, JobRef] = {}
        for query in filters.queries:
            for location in filters.locations or [""]:
                if len(found) >= filters.limit:
                    break
                self._search(query, location, filters.limit, found)
        return list(found.values())[: filters.limit]

    def _search(self, query: str, location: str, limit: int, found: dict[str, JobRef]) -> None:
        start = 0
        while len(found) < limit:
            data = self.client.get_json(
                f"{BASE}/api/pcsx/search",
                params={
                    "domain": DOMAIN,
                    "query": query,
                    "location": location,
                    "start": start,
                    "sort_by": "timestamp",
                },
                headers={"Referer": f"{BASE}/careers"},
            )["data"]
            positions = data.get("positions", [])
            if not positions:
                return
            for pos in positions:
                external_id = str(pos["id"])
                if external_id in found or title_excluded(pos.get("name") or ""):
                    continue
                found[external_id] = JobRef(
                    external_id=external_id,
                    url=f"{BASE}{pos['positionUrl']}",
                    hints={"title": pos.get("name")},
                )
                if len(found) >= limit:
                    return
            start += len(positions)
            if start >= data.get("count", 0):
                return

    def fetch(self, ref: JobRef) -> RawJob:
        data = self.client.get_json(
            f"{BASE}/api/pcsx/position_details",
            params={"position_id": ref.external_id, "domain": DOMAIN, "hl": "en"},
            headers={"Referer": ref.url},
        )["data"]
        lines = html_to_lines(data.get("jobDescription", ""))
        return RawJob(ref=ref, content="\n".join(lines), fields=data)

    def normalize(self, raw: RawJob) -> dict:
        f = raw.fields
        title = f.get("name") or raw.ref.hints.get("title") or "Unknown title"
        employment_type, employment_raw = _employment_type(f, title)
        posted_ts = f.get("postedTs")
        sections = parse_sections(raw.content.splitlines())
        return {
            "title": title,
            "requisition_id": f.get("displayJobId"),
            "employment_type": employment_type,
            "employment_type_raw": employment_raw,
            "work_mode": _WORK_MODE.get(str(f.get("workLocationOption") or "").lower()),
            "locations": f.get("locations") or [],
            "department": f.get("department"),
            "posted_date": datetime.fromtimestamp(posted_ts, UTC).date() if posted_ts else None,
            "description_text": raw.content,
            **sections,
        }
