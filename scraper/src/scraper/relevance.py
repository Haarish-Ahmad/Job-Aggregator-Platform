"""Shared filter: keep only software roles that an undergrad could realistically apply for.

Every adapter goes through this (via the pipeline), so a new site gets the filter for free.
Rules are deliberately strict: a posting with no entry-level signal is dropped.
"""

import re
from dataclasses import dataclass

from scraper.models import JobRecord

_NON_SOFTWARE = re.compile(
    r"\b(marketing|designer|ux|ui/ux|graphic design|product design|design lead|sales|"
    r"account (executive|manager)|recruit\w*|talent|human resources|hr|finance|financial|"
    r"legal|counsel|attorney|account(ant|ing)|payroll|business development|"
    r"customer (success|support|service)|support specialist|content|copywriter|brand|"
    r"communications|public relations|partnerships?|procurement|supply chain|logistics|"
    r"videographer|photographer|writer|editor|product manager|program manager|project manager|"
    r"management|mechanical|civil|chemical|manufacturing|facilit\w+|hardware|electrical|"
    r"silicon|asic|vlsi|strategist|physical security|design verification|verification engineer|"
    r"technical support|support engineer\w*|specialist|consultant|consulting|"
    r"annotation|data entry|bookkeep\w*|contributor|transcription|translator)\b",
    re.IGNORECASE,
)

_SENIOR = re.compile(
    r"\b(senior|senio\w*|sr|snr|staff|principal|lead|manager|director|head of|vp|vice president|architect|"
    r"distinguished|ii|iii|iv)\b|\b(sde|swe|engineer|developer|scientist)\s*[2-9]\b",
    re.IGNORECASE,
)

# Work-authorization restricted roles (we want roles open to Indian applicants).
_RESTRICTED = re.compile(
    r"\b(u\.?s\.? citizen(ship)?|security clearance|clearance|ts/sci|top secret|green card|visa required)\b",
    re.IGNORECASE,
)

# Roles that need a graduate degree are not for undergrads.
_GRAD_ONLY = re.compile(r"\b(ph\.?d\.?|postdoc|post[- ]doc|doctoral|doctorate)\b", re.IGNORECASE)

_ENTRY = re.compile(
    r"\b(interns?|internships?|new[- ]?grads?|new[- ]?hire|graduate|graduates?|entry[- ]level|campus|university|"
    r"apprentice|trainee|early[- ]career|junior|jr|freshers?|early talent)\b|"
    r"\b(sde|swe|engineer|developer)\s*[-]?\s*(i|1)\b",
    re.IGNORECASE,
)

_SOFTWARE_TITLE = re.compile(
    r"\b(software|swe|sde|engineer\w*|developer|programmer|full[- ]?stack|front[- ]?end|"
    r"back[- ]?end|devops|sre|machine learning|ml|ai|artificial intelligence|deep learning|nlp|"
    r"computer vision|llm|gen ?ai|generative|mlops|data scien\w+|data analy\w+|data engineer\w*|"
    r"business intelligence|bi developer|(security|soc|threat|cyber|ml|ai|python|sql|research) analyst|"
    r"cyber\w*|infosec|(information|network|application|cloud|product|it|data) security|pen ?test\w*|penetration|"
    r"vapt|appsec|"
    r"computer science|cloud|mobile|android|ios|web|qa|sdet|firmware|embedded|iot|robotics|blockchain|"
    r"applied scientist|research scientist)\b",
    re.IGNORECASE,
)

# Fallback for vague titles like "Research Intern": look at what the posting asks for.
_SOFTWARE_TEXT = re.compile(
    r"\b(software|programming|python|java|c\+\+|algorithms|data structures|machine learning|"
    r"deep learning|coding|computer science|sql|tensorflow|pytorch|cyber ?security|network security|"
    r"penetration testing|information security)\b",
    re.IGNORECASE,
)

_YEARS = re.compile(r"(\d{1,2})\s*(?:\+|-\s*\d{1,2}|to\s*\d{1,2}|or more)?\s*years?", re.IGNORECASE)


@dataclass
class Verdict:
    ok: bool
    reason: str = ""


def min_years_from_text(text: str) -> int | None:
    """Smallest 'N years' mentioned in a requirements text (alternatives are treated generously)."""
    years = [int(m) for m in _YEARS.findall(text) if int(m) <= 15]
    return min(years) if years else None


# "2 years ..., or 1 year with an advanced degree": the second clause is not for undergrads.
_ADVANCED_ALTERNATIVE = re.compile(
    r"[,;]?\s*\bor\b[^.;]*?\b(advanced degree|master|doctorate|ph\.?d)[^.;]*", re.IGNORECASE
)
_DEGREE_ABOVE_BACHELORS = re.compile(r"\b(master|doctorate|ph\.?d)", re.IGNORECASE)
_BACHELORS = re.compile(r"\bbachelor", re.IGNORECASE)


def min_years_from_items(items: list[str]) -> int | None:
    """Experience an undergrad needs, from a list of requirement lines.

    Postings list alternatives ("Bachelor's AND 4+ years, OR Master's AND 1+ year, OR Doctorate ...").
    Taking the smallest number would let a PhD path hide a 4-year requirement, so lines that
    only apply to a Master's/Doctorate are ignored.
    """
    years = []
    for item in items:
        if _DEGREE_ABOVE_BACHELORS.search(item) and not _BACHELORS.search(item):
            continue
        found = min_years_from_text(_ADVANCED_ALTERNATIVE.sub("", item))
        if found is not None:
            years.append(found)
    return min(years) if years else None


def title_excluded(title: str) -> str | None:
    """Cheap check on the title alone, usable before fetching a posting's detail."""
    if _NON_SOFTWARE.search(title):
        return "non-software role"
    if _SENIOR.search(title):
        return "senior role"
    if _GRAD_ONLY.search(title):
        return "graduate-degree role"
    if _RESTRICTED.search(title):
        return "work-authorization restricted"
    return None


def too_experienced(title: str, is_internship: bool, min_years: int | None) -> bool:
    """True when the posting clearly wants experience and shows no entry-level signal."""
    return not (is_internship or _ENTRY.search(title)) and min_years is not None and min_years > 1


def assess(record: JobRecord, software_trusted: bool = False) -> Verdict:
    """software_trusted: the source already restricts results to software (e.g. Internshala's CS category)."""
    reason = title_excluded(record.title)
    if reason:
        return Verdict(False, reason)
    if record.department and _NON_SOFTWARE.search(record.department):
        return Verdict(False, "non-software department")
    if not software_trusted:
        required_text = " ".join(record.required_qualifications)
        if not (
            _SOFTWARE_TITLE.search(f"{record.title} {record.department or ''}")
            or _SOFTWARE_TEXT.search(required_text)
        ):
            return Verdict(False, "not a software role")
    is_internship = record.employment_type.value == "internship"
    years = record.min_experience_years
    if too_experienced(record.title, is_internship, years):
        return Verdict(False, f"requires {years}+ years")
    if not (is_internship or _ENTRY.search(record.title)) and years is None:
        return Verdict(False, "no entry-level signal")
    return Verdict(True)
