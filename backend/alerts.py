"""Email alerts: opt-in students get a digest of new, good matches. SMTP comes from env (Mailpit in dev)."""
import logging
import smtplib
from datetime import datetime
from collections.abc import Sequence
from email.message import EmailMessage

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import Settings, get_settings
from db import get_db
from deps import ingest_auth
from matching import compute_matches, save_matches
from metrics import ALERT_EMAILS
from models import Job, Match, Students

log = logging.getLogger(__name__)
router = APIRouter()


def build_message(student: Students, rows: Sequence[tuple[Match, Job]], settings: Settings) -> EmailMessage:
    shown = rows[: settings.alert_max_jobs_per_email]
    lines = [f"Hi {student.name},", "", f"{len(rows)} new job(s) match your profile:", ""]
    for match, job in shown:
        lines.append(f"- {job.title} at {job.company_name} ({match.score:.0f}% match)")
        lines.append(f"  {settings.public_url.rstrip('/')}/jobs/{job.id}")
    if len(rows) > len(shown):
        lines.append(f"...and {len(rows) - len(shown)} more.")
    lines += ["", "You get this because job alerts are switched on in your profile; you can switch them off there."]
    msg = EmailMessage()
    msg["Subject"] = f"{len(rows)} new job match{'es' if len(rows) != 1 else ''} for you"
    msg["From"] = settings.mail_from
    msg["To"] = student.email
    msg.set_content("\n".join(lines))
    return msg


def send_email(msg: EmailMessage, settings: Settings) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def run_alerts(db: Session, settings: Settings, sender=None) -> dict:
    """Refresh matches for every opted-in student and email the ones not yet notified."""
    sender = sender or send_email  # resolved at call time so tests can replace send_email
    summary = {"students": 0, "emails_sent": 0, "emails_failed": 0, "matches_notified": 0}
    students = db.scalars(select(Students).where(Students.alerts_enabled.is_(True))).all()
    for student in students:
        summary["students"] += 1
        save_matches(student, compute_matches(student, db), db)
        db.commit()
        rows = [(m, j) for m, j in db.execute(
            select(Match, Job).join(Job, Job.id == Match.job_id)
            .where(Match.student_id == student.id, Match.notified_at.is_(None),
                   Match.score >= settings.alert_min_score, Job.is_active.is_(True))
            .order_by(Match.score.desc(), Job.id.desc())
        )]
        if not rows:
            continue
        try:
            sender(build_message(student, rows, settings), settings)
        except Exception:
            # One unreachable mailbox / SMTP hiccup must not stop the other students' emails.
            log.exception("alert email to student %s failed", student.id)
            summary["emails_failed"] += 1
            ALERT_EMAILS.labels("failed").inc()
            continue
        now = datetime.now()
        for match, _ in rows:
            match.notified_at = now
        db.commit()
        summary["emails_sent"] += 1
        summary["matches_notified"] += len(rows)
        ALERT_EMAILS.labels("sent").inc()
    return summary


@router.post("/internal/alerts/run")
def trigger_alerts(auth=Depends(ingest_auth), db: Session = Depends(get_db)):
    return run_alerts(db, get_settings())
