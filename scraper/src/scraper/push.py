"""Send scraped jobs to the backend's POST /internal/jobs.

to_payload() maps a JobRecord onto the backend's ingest schema and makes every value fit the backend's
column sizes (the backend also checks them, per record, but a record should rarely be rejected).
BackendPusher batches records, retries transport errors, and turns the backend's per-record answers into stats
and dead-letter entries, so one bad record never stops a run.
"""
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from scraper.config import Settings
from scraper.location import in_india
from scraper.metrics import PUSH_BATCHES, PUSHED
from scraper.models import FailedJob, JobRecord, WorkMode
from scraper.storage.base import Storage

log = logging.getLogger(__name__)

# Backend column sizes (backend/schemas.py FIELD_LIMITS). Keep in sync.
MAX_COMPANY = 100
MAX_TITLE = 255
MAX_LOCATION = 150
MAX_URL = 500
MAX_EXTERNAL_ID = 255
MAX_JOB_TYPE = 30
MAX_SKILLS = 30
MAX_SKILL_CHARS = 40

_REMOTE = re.compile(r"\b(remote|wfh|work[ -]from[ -]home|anywhere)\b", re.IGNORECASE)
# Countries a posting on an Indian job board might name when it is *not* in India.
_FOREIGN = re.compile(
    r"\b(usa|u\.s\.a?\.?|united states|uk|united kingdom|england|canada|germany|france|netherlands|ireland|singapore|"
    r"australia|new zealand|dubai|uae|saudi|qatar|japan|china|hong kong|brazil|mexico|sweden|spain|italy|poland|"
    r"israel|nepal|bangladesh|sri lanka|malaysia|indonesia|philippines|egypt|nigeria|kenya)\b",
    re.IGNORECASE,
)
# Bullet text that is a requirement sentence, not a skill name.
_NOT_A_SKILL = re.compile(
    r"\b(degree|experience|years?|ability|abilities|knowledge|proficien\w*|strong|excellent|must|should|required|"
    r"preferred|minimum|familiar\w*|understanding|bachelor\w*|master\w*|equivalent|plus|etc)\b",
    re.IGNORECASE,
)


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _truncate(text: str, limit: int) -> str:
    """Cut at a word boundary and mark the cut."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0] or text[: limit - 1]
    return cut.rstrip(" ,;-") + "…"


def join_locations(locations: list[str]) -> str | None:
    """'A, B, C' within the backend's limit; the places that do not fit become '+N more'."""
    places = list(dict.fromkeys(p for p in (_clean(x) for x in locations) if p))
    if not places:
        return None
    full = ", ".join(places)
    if len(full) <= MAX_LOCATION:
        return full
    kept: list[str] = []
    for place in places:
        remaining = len(places) - len(kept)
        suffix = f", +{remaining} more"
        if len(", ".join([*kept, place])) + len(suffix) > MAX_LOCATION:
            break
        kept.append(place)
    if not kept:  # a single huge place name
        return _truncate(places[0], MAX_LOCATION)
    return f"{', '.join(kept)}, +{len(places) - len(kept)} more"


def clean_skill_list(items: list[str]) -> list[str]:
    """Short skill-like phrases only: drops requirement sentences, dedupes, caps the count."""
    skills: dict[str, None] = {}
    for item in items:
        skill = _clean(item).strip("•-–—*· ").rstrip(".;,")
        words = skill.split()
        if not (2 <= len(skill) <= MAX_SKILL_CHARS) or len(words) > 4 or ":" in skill or _NOT_A_SKILL.search(skill):
            continue
        skills.setdefault(skill.lower(), None)
    return list(skills)[:MAX_SKILLS]


def _apply_url(url: str) -> str | None:
    if len(url) <= MAX_URL:
        return url
    parts = urlsplit(url)
    bare = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))  # drop a tracking query string
    return bare if len(bare) <= MAX_URL else None


def is_remote(record: JobRecord) -> bool:
    mode = record.work_mode or (record.extraction.data.work_mode if record.extraction else None)
    return mode == WorkMode.remote or any(_REMOTE.search(loc) for loc in record.locations) or bool(_REMOTE.search(record.title))


def india_flag(record: JobRecord, india_portal: bool) -> bool | None:
    """True/False when the place is known, None when the posting names no place (e.g. remote only)."""
    places = [loc for loc in record.locations if _clean(loc) and not _REMOTE.fullmatch(_clean(loc))]
    if not places:
        return None
    if any(in_india(p) for p in places):
        return True
    foreign = any(_FOREIGN.search(p) for p in places)
    if india_portal and not foreign:
        return True  # an Indian job board's small-town location the city list does not know
    return False


def to_payload(record: JobRecord, india_portal: bool = False) -> dict | None:
    """The backend's jobsIn for a record, or None when it cannot be represented (e.g. an unusable URL)."""
    url = _apply_url(record.url)
    company, title = _truncate(_clean(record.company), MAX_COMPANY), _truncate(_clean(record.title), MAX_TITLE)
    if not (url and company and title and len(record.external_id) <= MAX_EXTERNAL_ID):
        return None
    extraction = record.extraction.data if record.extraction else None
    skills = clean_skill_list(extraction.skills) if extraction and extraction.skills else clean_skill_list(record.required_qualifications)
    overview = _clean(record.overview)
    description = "\n\n".join(p for p in (overview, record.description_text.strip()) if p) or None
    mode = record.work_mode or (extraction.work_mode if extraction else None)
    employment = None if record.employment_type.value == "unknown" else record.employment_type.value
    return {
        "company_name": company,
        "title": title,
        "apply_url": url,
        "location": join_locations(record.locations),
        "job_type": employment[:MAX_JOB_TYPE] if employment else None,
        "description": description,
        "allowed_grads": sorted({y for y in (extraction.graduation_years if extraction else []) if 2000 <= y <= 2100}),
        "required_skills": skills,
        "source": record.source,
        "external_id": record.external_id,
        "source_content_hash": record.content_hash,
        "is_remote": is_remote(record),
        "is_india": india_flag(record, india_portal),
        "work_mode": mode.value if mode else None,
        "posted_date": record.posted_date.isoformat() if record.posted_date else None,
    }


class PushError(Exception):
    """The backend refused us outright (bad token, unreachable): retrying the same batch will not help."""


@dataclass
class PushStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0
    failed: int = 0   # not delivered (backend unreachable / refused); re-sent on the next run
    dropped: int = 0  # could not be mapped onto the backend schema
    reasons: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        return (f"inserted={self.inserted} updated={self.updated} unchanged={self.unchanged} "
                f"rejected={self.rejected} failed={self.failed} dropped={self.dropped}")


class BackendPusher:
    def __init__(self, settings: Settings, storage: Storage, client: httpx.Client | None = None, india_portal: bool = False):
        self.settings = settings
        self.storage = storage
        self.india_portal = india_portal
        self.stats = PushStats()
        self._buffer: list[tuple[JobRecord, dict]] = []
        self._lock = threading.Lock()
        self._fatal: str | None = None
        self._client = client or httpx.Client(base_url=settings.backend_url.rstrip("/"), timeout=settings.backend_timeout_seconds)

    def add(self, record: JobRecord) -> None:
        payload = to_payload(record, self.india_portal)
        with self._lock:
            if payload is None:
                self.stats.dropped += 1
                PUSHED.labels("dropped").inc()
                self._dead_letter(record, "cannot be mapped to the backend schema (empty field or URL too long)")
                return
            self._buffer.append((record, payload))
            if len(self._buffer) >= self.settings.ingest_batch_size:
                self._flush_locked()

    def flush(self) -> PushStats:
        with self._lock:
            self._flush_locked()
        return self.stats

    def _flush_locked(self) -> None:
        while self._buffer:
            batch, self._buffer = self._buffer[: self.settings.ingest_batch_size], self._buffer[self.settings.ingest_batch_size :]
            self._send(batch)

    @retry(retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)), stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, max=10), reraise=True)
    def _post(self, payloads: list[dict]) -> dict:
        resp = self._client.post("/internal/jobs", json={"jobs": payloads}, headers={"X-Ingest-Token": self.settings.ingest_token})
        if resp.status_code in (401, 403):
            raise PushError(f"backend refused the ingest token (HTTP {resp.status_code}); check INGEST_TOKEN")
        if resp.status_code >= 500:
            resp.raise_for_status()  # retried
        if resp.status_code >= 400:
            raise ValueError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def _send(self, batch: list[tuple[JobRecord, dict]]) -> None:
        if self._fatal:
            self._fail(batch, self._fatal)
            return
        try:
            body = self._post([p for _, p in batch])
        except PushError as exc:
            self._fatal = str(exc)  # every later batch would fail the same way
            log.error("%s", exc)
            PUSH_BATCHES.labels("failed").inc()
            self._fail(batch, self._fatal)
            return
        except ValueError as exc:
            if len(batch) > 1:  # the backend rejected the whole request shape: isolate the culprit
                log.warning("batch rejected (%s); retrying its %d records one by one", exc, len(batch))
                for single in batch:
                    self._send([single])
                return
            PUSH_BATCHES.labels("failed").inc()
            self._reject(batch[0][0], f"backend rejected the record: {exc}")
            return
        except Exception as exc:
            log.error("could not reach the backend: %s", exc)
            PUSH_BATCHES.labels("failed").inc()
            self._fail(batch, f"{type(exc).__name__}: {exc}")
            return
        PUSH_BATCHES.labels("ok").inc()
        for (record, _), result in zip(batch, body["results"], strict=True):
            status = result["status"]
            PUSHED.labels(status).inc()
            if status == "rejected":
                self._reject(record, result.get("reason") or "rejected by the backend")
            elif status == "unchanged":
                self.stats.unchanged += 1
            else:
                setattr(self.stats, status, getattr(self.stats, status) + 1)

    def _reject(self, record: JobRecord, reason: str) -> None:
        self.stats.rejected += 1
        self.stats.reasons[reason.split(" (")[0]] = self.stats.reasons.get(reason.split(" (")[0], 0) + 1
        log.warning("backend rejected %s/%s: %s", record.source, record.external_id, reason)
        self._dead_letter(record, reason)

    def _fail(self, batch: list[tuple[JobRecord, dict]], error: str) -> None:
        for record, _ in batch:
            self.stats.failed += 1
            PUSHED.labels("failed").inc()
            self._dead_letter(record, error)

    def _dead_letter(self, record: JobRecord, error: str) -> None:
        self.storage.save_failure(FailedJob(source=record.source, external_id=record.external_id, url=record.url,
                                            stage="ingest", error=error[:500], at=datetime.now(UTC)))

    def close(self) -> None:
        self._client.close()
