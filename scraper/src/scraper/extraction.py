"""LLM extraction stage: asks a local Ollama model to read a posting and fill JobExtraction.

The model is never trusted blindly. Everything it returns is checked against the posting text
(`ground`), and anything it cannot back up is dropped. Code-set fields are never touched here.
"""

import logging
import re
from datetime import UTC, datetime

import httpx
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from scraper.config import Settings
from scraper.models import ExtractionResult, JobExtraction

log = logging.getLogger(__name__)

PROMPT_VERSION = "v4"

SYSTEM_PROMPT = """You extract facts from a job posting into JSON. Rules:
- Use ONLY what the posting text says. If something is not stated, use null (or [] for lists).
- skills: ONLY specific technologies, programming languages, tools, frameworks or named techniques (e.g. Python, SQL, AWS, React, machine learning). Never general phrases like "customer perspective" or "innovative methods". Do not invent any.
- degree_required: the minimum degree asked for (bachelors/masters/phd). If several levels are listed as alternatives (e.g. "Master's or Doctorate"), give the LOWEST one. Use "none" ONLY if the posting explicitly says no degree is required; otherwise null if unstated.
- graduation_years: batch/graduation years the posting targets (e.g. "2026 graduates" -> [2026]).
- work_mode: onsite, hybrid or remote, only if stated.
- salary_*: copy the pay figures exactly as written, with NO arithmetic, and put the unit word in salary_unit. "10 lakh - 25 lakh per year" -> salary_min 10, salary_max 25, salary_unit "lakh", salary_currency "INR", salary_period "year". "$135K" -> 135 with unit "thousand". "50000" -> 50000 with unit null. Null everywhere if the posting gives no pay.
- work_authorization_restricted: true ONLY if the posting says applicants must be citizens/residents of a country or authorized to work in one. Copy that exact sentence into work_authorization_note. Otherwise null.
Return JSON only."""


class ExtractionError(Exception):
    pass


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _number_in_text(value: float, text: str) -> bool:
    plain = text.replace(",", "").replace(" ", "").lower()
    return str(int(value)) in plain or f"{value:g}" in plain


_UNIT_FACTOR = {"thousand": 1_000, "lakh": 100_000, "crore": 10_000_000, "million": 1_000_000}
_UNIT_EVIDENCE = {
    "thousand": re.compile(r"\dk\b|thousand", re.I),
    "lakh": re.compile(r"lakh|\blacs?\b|\blpa\b", re.I),
    "crore": re.compile(r"crore|\dcr\b", re.I),
    "million": re.compile(r"million|\dm\b", re.I),
}


# A degree level is only believed if the posting uses a word that points to it.
_DEGREE_EVIDENCE = {
    "bachelors": re.compile(r"bachelor|b\.?\s?tech|\bb\.?e\.?\b|\bb\.?s\.?c?\b|undergrad|\bbca\b", re.I),
    "masters": re.compile(r"master|m\.?\s?tech|\bm\.?s\.?c?\b|\bmba\b|\bmca\b", re.I),
    "phd": re.compile(r"ph\.?\s?d|doctora", re.I),
    "none": re.compile(r"no (formal )?degree|degree (is )?not (required|needed|necessary)|without a degree", re.I),
}


def ground(data: JobExtraction, text: str) -> JobExtraction:
    """Drop anything the posting text does not support. Small models hallucinate; this keeps the output honest."""
    haystack = _norm(text)
    grounded = {_norm(s): s.strip() for s in reversed(data.skills) if s.strip() and _norm(s) in haystack}
    data.skills = list(reversed(grounded.values()))[:30]  # case-insensitive dedupe, first spelling kept
    data.graduation_years = [y for y in dict.fromkeys(data.graduation_years) if 2000 <= y <= 2100 and str(y) in text]

    note = _norm(data.work_authorization_note or "")
    if not note or note not in haystack:
        data.work_authorization_note = None
        data.work_authorization_restricted = None  # a restriction we cannot quote is not a restriction
    if data.work_authorization_restricted is not True:
        data.work_authorization_restricted = None
        data.work_authorization_note = None

    if data.degree_required and not _DEGREE_EVIDENCE[data.degree_required].search(text):
        data.degree_required = None

    amounts = [a for a in (data.salary_min, data.salary_max) if a is not None]
    unit = data.salary_unit
    data.salary_unit = None
    unit_ok = unit is None or _UNIT_EVIDENCE[unit].search(text)
    if any(a <= 0 or not _number_in_text(a, text) for a in amounts) or not unit_ok:
        data.salary_min = data.salary_max = data.salary_currency = data.salary_period = None
    elif amounts and unit:
        factor = _UNIT_FACTOR[unit]
        data.salary_min = data.salary_min * factor if data.salary_min is not None else None
        data.salary_max = data.salary_max * factor if data.salary_max is not None else None
    if not amounts:
        data.salary_currency = data.salary_period = None  # currency/period without a figure means nothing
    elif data.salary_min is not None and data.salary_max is not None and data.salary_min > data.salary_max:
        data.salary_min, data.salary_max = data.salary_max, data.salary_min
    return data


class OllamaExtractor:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client or httpx.Client(timeout=settings.ollama_timeout_seconds)

    @property
    def tag(self) -> str:
        """Identifies model + prompt; a stored extraction with a different tag is stale."""
        return f"{self.settings.ollama_model}|{PROMPT_VERSION}"

    def wants(self, description_text: str) -> bool:
        return len(description_text) >= self.settings.extraction_min_chars

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, max=20),
        reraise=True,
    )
    def _chat(self, title: str, text: str) -> str:
        resp = self._client.post(
            f"{self.settings.ollama_url.rstrip('/')}/api/chat",
            json={
                "model": self.settings.ollama_model,
                "stream": False,
                "format": JobExtraction.model_json_schema(),
                "options": {"temperature": 0, "num_ctx": self.settings.ollama_num_ctx},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Job title: {title}\n\nPosting:\n{text}"},
                ],
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def extract(self, title: str, description_text: str) -> ExtractionResult:
        text = description_text[: self.settings.extraction_max_chars]
        last_error: Exception | None = None
        for attempt in (1, 2):  # one repair attempt if the model returns invalid JSON
            content = self._chat(title, text)
            try:
                data = JobExtraction.model_validate_json(content)
                break
            except ValidationError as exc:
                last_error = exc
                log.warning("extraction attempt %d for %r returned invalid output", attempt, title)
        else:
            raise ExtractionError(f"model output failed validation twice: {last_error}")
        return ExtractionResult(
            model=self.settings.ollama_model,
            prompt_version=PROMPT_VERSION,
            extracted_at=datetime.now(UTC),
            data=ground(data, text),
        )

    def close(self) -> None:
        self._client.close()
