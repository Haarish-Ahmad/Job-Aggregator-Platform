"""Bulk job ingest: per-record validation, upsert on (source, external_id), legacy hash dedup.

Each record is handled in its own SAVEPOINT, so one bad record (or a race on a unique key)
is reported in the results and never fails or rolls back the rest of the batch.
"""
import hashlib
import logging
from datetime import datetime
from urllib.parse import urlsplit

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from models import Companies, Job
from schemas import FIELD_LIMITS, RecordResult, Status, ingestionResult, jobsIn

log = logging.getLogger(__name__)


def make_hash(company: str, title: str, location: str | None) -> str:
    raw = f"{company}|{title}|{location or ''}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()


def identity_hash(source: str, external_id: str) -> str:
    """Value of the unique content_hash column for a scraped posting."""
    return hashlib.sha256(f"{source}|{external_id}".encode()).hexdigest()


def fallback_content_hash(item: jobsIn) -> str:
    """Freshness fingerprint when the client did not send source_content_hash."""
    parts = [item.title, item.description or "", item.location or "", item.apply_url, item.job_type or "",
             ",".join(item.required_skills), str(item.deadline or "")]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def validate_record(item: jobsIn) -> str | None:
    """Reason the record cannot be stored, or None. Size limits mirror the column sizes."""
    for field, limit in FIELD_LIMITS.items():
        value = getattr(item, field)
        if value is not None and len(value) > limit:
            return f"{field} too long ({len(value)} > {limit})"
    if not item.company_name.strip():
        return "company_name is blank"
    if not item.title.strip():
        return "title is blank"
    if urlsplit(item.apply_url).scheme not in ("http", "https"):
        return "apply_url must start with http:// or https://"
    if bool(item.source) != bool(item.external_id):
        return "source and external_id must be sent together"
    if item.min_cgpa is not None and not 0 <= item.min_cgpa <= 10:
        return "min_cgpa must be between 0 and 10"
    return None


def _careers_url(apply_url: str) -> str:
    """A new company's careers_url: the site the posting lives on (the posting link itself is not a careers page)."""
    parts = urlsplit(apply_url)
    return f"{parts.scheme}://{parts.netloc}/"[:255]


def _get_or_create_company(db: Session, item: jobsIn) -> Companies:
    company = db.scalars(
        select(Companies).where(func.lower(Companies.company_name) == item.company_name.strip().lower())
    ).first()
    if not company:
        company = Companies(company_name=item.company_name.strip(), careers_url=_careers_url(item.apply_url),
                            description=item.description)
        db.add(company)
        db.flush()
    return company


def _apply(job: Job, item: jobsIn, company_id: int) -> None:
    job.company_id = company_id
    job.title = item.title
    job.description = item.description
    job.location = item.location
    job.job_type = item.job_type
    job.min_cgpa = item.min_cgpa
    job.allowed_branches = item.allowed_branches
    job.allowed_grads = item.allowed_grads
    job.necessary_skills = item.required_skills
    job.apply_url = item.apply_url
    job.deadline_at = item.deadline
    job.is_remote = item.is_remote
    job.is_india = item.is_india
    job.work_mode = item.work_mode
    job.posted_date = item.posted_date


def _upsert(db: Session, item: jobsIn) -> tuple[Status, int | None]:
    now = datetime.now()
    company = _get_or_create_company(db, item)
    if item.source and item.external_id:
        digest = item.source_content_hash or fallback_content_hash(item)
        job = db.scalars(select(Job).where(Job.source == item.source, Job.external_id == item.external_id)).first()
        if job:
            job.last_seen_at = now
            job.is_active = True  # seen again, so it is open again
            if job.source_content_hash == digest:
                return "unchanged", job.id
            _apply(job, item, company.id)
            job.source_content_hash = digest
            job.updated_at = now
            job.scraped_at = now
            db.flush()
            return "updated", job.id
        job = Job(content_hash=identity_hash(item.source, item.external_id), source=item.source,
                  external_id=item.external_id, source_content_hash=digest, last_seen_at=now, updated_at=now)
        _apply(job, item, company.id)
        db.add(job)
        db.flush()
        return "inserted", job.id
    # Legacy payload without a source identity: dedup on company|title|location as before.
    digest = make_hash(item.company_name, item.title, item.location)
    existing = db.scalars(select(Job).where(Job.content_hash == digest)).first()
    if existing:
        existing.last_seen_at = now
        return "unchanged", existing.id
    job = Job(content_hash=digest, last_seen_at=now, updated_at=now)
    _apply(job, item, company.id)
    db.add(job)
    db.flush()
    return "inserted", job.id


def deactivate_stale(db: Session, days: int) -> int:
    """Mark scraped postings not seen for `days` days as inactive; returns how many. Hand-added jobs are left alone."""
    result = db.execute(
        text("""UPDATE job_postings SET is_active = false
                WHERE is_active AND source IS NOT NULL AND last_seen_at < now() - make_interval(days => :days)"""),
        {"days": days},
    )
    db.commit()
    return getattr(result, "rowcount", 0)


def ingest(db: Session, items: list[jobsIn]) -> ingestionResult:
    results: list[RecordResult] = []
    for index, item in enumerate(items):
        reason = validate_record(item)
        if reason:
            results.append(RecordResult(index=index, status="rejected", reason=reason))
            continue
        try:
            with db.begin_nested():
                status, job_id = _upsert(db, item)
            results.append(RecordResult(index=index, status=status, job_id=job_id))
        except IntegrityError:
            # Lost a race with a concurrent ingest of the same posting: it exists now, so it is a duplicate.
            db.expire_all()
            results.append(RecordResult(index=index, status="unchanged", reason="already ingested concurrently"))
        except SQLAlchemyError as exc:
            log.exception("ingest failed for record %d", index)
            results.append(RecordResult(index=index, status="rejected", reason=f"database error: {type(exc).__name__}"))
    db.commit()
    count = lambda status: sum(1 for r in results if r.status == status)  # noqa: E731
    return ingestionResult(inserted=count("inserted"), updated=count("updated"),
                           skipped=count("unchanged"), rejected=count("rejected"), results=results)
