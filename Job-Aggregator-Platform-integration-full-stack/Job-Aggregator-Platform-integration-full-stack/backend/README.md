# Job Aggregator Platform: backend

FastAPI + SQLAlchemy + PostgreSQL. Students register, the scraper ingests jobs, and each student gets a ranked list of matching
jobs, optional email alerts, and the placement cell gets analytics. The 42 manual API cases are in [testcases.md](testcases.md)
(automated in `tests/test_testcases.py`).

## Run locally

```bash
# a Postgres to talk to (matches the dev defaults below)
docker run -d --name jobs-pg -e POSTGRES_USER=jobs -e POSTGRES_PASSWORD=jobs -e POSTGRES_DB=jobs -p 5432:5432 postgres:16-alpine

pip install -r ../requirements.txt          # from this directory; pinned versions
export APP_ENV=dev                          # relaxes the startup checks below (defaults SECRET_KEY / DATABASE_URL)
alembic upgrade head
uvicorn main:app --reload
```

The API runs at `http://localhost:8000`. Interactive docs are at `http://localhost:8000/docs`.
In the full stack it is served at `/api/` behind nginx; see the repository README.

## Configuration

All settings are environment variables (read by `config.py`, optional `backend/.env`).

| Variable | Default | |
|---|---|---|
| `APP_ENV` | `production` | `dev` fills in a default `SECRET_KEY` and `DATABASE_URL`. **Anything else refuses to start** without a private `SECRET_KEY` and a `DATABASE_URL`. |
| `DATABASE_URL` | dev: `postgresql://jobs:jobs@localhost:5432/jobs` | SQLAlchemy URL |
| `SECRET_KEY` | dev only: `dev-secret-change-me` | Signs the session cookie |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost` | Allowed browser origins |
| `SESSION_COOKIE_SECURE` | `false` | `true` behind HTTPS |
| `INGEST_TOKEN` | empty (token auth off) | Value of the `X-Ingest-Token` header accepted by `/internal/*` |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | empty | Used by `python cli.py bootstrap-admin` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, `MAIL_FROM` | `localhost`, `1025` | Alert emails |
| `ALERT_MIN_SCORE`, `ALERT_MAX_JOBS_PER_EMAIL`, `PUBLIC_URL` | `60`, `20`, `http://localhost` | Alert content |
| `STALE_DAYS` | `14` | `deactivate-stale` threshold |
| `CURRICULUM_FILE` | `curriculum.yaml` | Courses used by `/analytics/curriculum` |
| `ROOT_PATH` | empty | Set to `/api` when served under that prefix (affects the docs only) |

## Commands

```bash
python cli.py bootstrap-admin    # create/update the admin from ADMIN_EMAIL + ADMIN_PASSWORD (idempotent; run on container start)
python cli.py deactivate-stale   # mark scraped postings not seen for STALE_DAYS as inactive
python cli.py send-alerts        # send pending job-match emails now
```

## API endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | /health | none | Health check (also checks the database; 503 if it is down) |
| GET | /metrics | none (internal; blocked by nginx) | Prometheus metrics |
| POST | /auth/register | none | Create a student account |
| POST | /auth/login | none | Log in, sets a session cookie |
| POST | /auth/logout | none | Clear the session |
| GET | /me | login | Current student profile |
| PATCH | /me/update | login | Update branch, cgpa, grad_year, skills, resume_link, alerts_enabled |
| GET | /me/matches | login | Eligible jobs ranked by skill match; `min_score`; 0% matches hidden unless `include_unmatched=true` |
| POST | /company | login | Create a company |
| GET | /companies | login | List companies |
| GET | /jobs | login | List jobs. Filters `q` (title or company), `company_id`, `job_type`, `location`, `skill`, `grad_year`, `source`, `scope`, `active_only`, `hide_expired`; `sort`; `limit` (1+, capped at 100) and `offset` (0+); total in the `X-Total-Count` header |
| GET | /jobs/{job_id} | login | Single job |
| GET | /analytics/skills | login | Most requested skills + weekly trend |
| GET | /analytics/companies | login | Top companies, mix by type/source, weekly volume |
| GET | /analytics/skill-gap | admin | Demand for a skill vs how many students have it |
| GET | /analytics/curriculum | admin | How much of what jobs ask for is taught (from `curriculum.yaml`) |
| POST | /internal/jobs | admin session **or** `X-Ingest-Token` | Bulk ingest (below) |
| POST | /internal/alerts/run | admin session or ingest token | Send pending alert emails |
| POST | /internal/maintenance/deactivate-stale | admin session or ingest token | Mark postings the scraper stopped seeing as inactive |

`scope` is `all` (default), `india`, `remote` or `india_remote`. Out-of-range pagination is a 422, except `limit` above 100, which is clamped.

## Ingest contract (`POST /internal/jobs`)

Body `{"jobs": [...]}` (at most 500). Each job needs `company_name`, `title`, `apply_url`; optional `location`, `job_type`, `description`,
`min_cgpa`, `allowed_branches`, `allowed_grads`, `required_skills`, `deadline`, plus the scraper fields
`source`, `external_id`, `source_content_hash`, `is_remote`, `is_india`, `work_mode`, `posted_date`.

* **Identity.** With `source` + `external_id` a posting is upserted on that pair. Without them the old
  `company|title|location` hash is used (nothing changes for existing callers).
* **Freshness.** Re-sending a known posting refreshes `last_seen_at`. A different `source_content_hash` updates the row in place.
* **Per-record results.** Response:
  `{"inserted":2,"updated":1,"skipped":3,"rejected":1,"results":[{"index":0,"status":"inserted|updated|unchanged|rejected","job_id":12,"reason":null}]}`.
  A record that is too long, has a non-http `apply_url`, or is otherwise unusable is `rejected` with a reason; it never fails the others.
* A malformed request (missing `title`, bad date format) is still a 422 for the whole request.

## Matching rules

A job is shown to a student only if all of these hold:

- The deadline has not passed.
- The student's CGPA is at least the job's `min_cgpa` (when set).
- The student's branch is in `allowed_branches` (when set).
- The student's `grad_year` is in `allowed_grads` (when set).

The score is the percentage of the job's required skills that the student has. A job with no required skills scores 100.
A job that scores 0 is not returned by `/me/matches` unless `include_unmatched=true`. This is rule-based matching, not machine learning.

## Tests

```bash
docker run -d --name jobs-test-pg -e POSTGRES_USER=jobs -e POSTGRES_PASSWORD=jobs -e POSTGRES_DB=jobs_test -p 5432:5432 postgres:16-alpine
pip install -r ../requirements-dev.txt
pytest                      # builds the schema with the real migrations; the 42 cases + ingest, alerts, analytics, config, CLI
ruff check . && mypy --ignore-missing-imports --explicit-package-bases --exclude 'alembic|tests' .
```
