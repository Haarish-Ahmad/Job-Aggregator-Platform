"""Operational commands. Run from the backend directory:

    python cli.py bootstrap-admin   create/update the admin from ADMIN_EMAIL + ADMIN_PASSWORD (idempotent)
    python cli.py deactivate-stale  mark scraped postings not seen for STALE_DAYS as inactive
    python cli.py send-alerts       send pending job-match emails now
"""
import argparse
import logging
import sys

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from config import get_settings
from db import session_local
from ingest import deactivate_stale as retire_stale_postings
from models import Students

log = logging.getLogger("cli")


def bootstrap_admin() -> int:
    settings = get_settings()
    if not (settings.admin_email and settings.admin_password):
        log.info("ADMIN_EMAIL / ADMIN_PASSWORD not set; skipping admin bootstrap")
        return 0
    try:
        # Same check the login form applies: an admin whose address it rejects could never sign in.
        validate_email(settings.admin_email, check_deliverability=False)
    except EmailNotValidError as exc:
        log.error("ADMIN_EMAIL %r is not usable (%s)", settings.admin_email, exc)
        return 1
    if len(settings.admin_password) < 8:
        log.error("ADMIN_PASSWORD must be at least 8 characters")
        return 1
    with session_local() as db:
        admin = db.scalars(select(Students).where(Students.email == settings.admin_email)).first()
        if admin:
            admin.role = "admin"
            admin.password_hash = generate_password_hash(settings.admin_password)
            action = "updated"
        else:
            db.add(Students(name="Admin", email=settings.admin_email, role="admin", grad_year=2000, skills=[],
                            password_hash=generate_password_hash(settings.admin_password)))
            action = "created"
        db.commit()
    log.info("admin %s: %s", action, settings.admin_email)
    return 0


def deactivate_stale() -> int:
    days = get_settings().stale_days
    with session_local() as db:
        count = retire_stale_postings(db, days)
    log.info("deactivated %d posting(s) not seen for %d days", count, days)
    return 0


def send_alerts() -> int:
    from alerts import run_alerts

    with session_local() as db:
        log.info("alerts: %s", run_alerts(db, get_settings()))
    return 0


COMMANDS = {"bootstrap-admin": bootstrap_admin, "deactivate-stale": deactivate_stale, "send-alerts": send_alerts}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=sorted(COMMANDS))
    return COMMANDS[parser.parse_args(argv).command]()


if __name__ == "__main__":
    sys.exit(main())
