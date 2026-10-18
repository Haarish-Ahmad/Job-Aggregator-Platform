# Plan

> **Status:** every task below is done; the checkboxes were ticked as work landed. Where reality differed from the plan,
> [DECISIONS.md](DECISIONS.md) says why (notably D11). The contract section is still accurate except that `source_content_hash`
> is computed by the scraper over everything it sends (not just the description).

Derived from [AUDIT.md](AUDIT.md) and the decisions in [DECISIONS.md](DECISIONS.md). Update the checkboxes as work lands.

## Layout

```
backend/        FastAPI app (teammate's; changed only where noted under "Backend changes")
scraper/        scraper service (kept in place; a long-running `serve` mode is added)
frontend/       React + Vite + TypeScript (nothing existed, so this stack per mission)
infra/          nginx, prometheus, grafana provisioning
docker-compose.yml · docker-compose.prod.yml · .env.example · .github/workflows/{ci,release}.yml
```

## Integration contract (scraper → backend)

`POST /internal/jobs`, header `X-Ingest-Token: $INGEST_TOKEN` (constant-time compare). The admin cookie session keeps working.

Request `{"jobs":[{…}]}`; each item keeps the existing `jobsIn` fields and gains optional:
`source`, `external_id`, `source_content_hash`, `is_remote`, `is_india`, `work_mode`, `posted_date`, `last_seen`.
Shape errors (missing `title`/`apply_url`/`company_name`, bad date) stay **422** for the whole request, exactly as
`testcases.md` TC-23/TC-24 require. Everything else is judged per record.

Response (additive; `inserted`/`skipped` unchanged so TC-21/22 hold):

```json
{"inserted":2,"updated":1,"skipped":3,"rejected":1,
 "results":[{"index":0,"status":"inserted|updated|unchanged|rejected","job_id":12,"reason":null}]}
```

Identity and freshness:

| Payload has | Identity | On repeat |
|---|---|---|
| `source` + `external_id` | unique `(source, external_id)` | same `source_content_hash` → `unchanged` (bump `last_seen_at`); different → `updated` |
| neither (legacy) | existing `company|title|location` hash | `skipped`, as today |

Records over a column limit are `rejected` with a reason instead of failing the batch; the scraper also truncates and
normalises before sending. Backend never 500s on a bad record.

Field mapping: `company`→`company_name`, `url`→`apply_url`, `locations`→`location` (joined, ≤150), `employment_type`→`job_type`,
`description_text`→`description`, extraction/qualification skills→`required_skills` (short phrases only), extracted
`graduation_years`→`allowed_grads`, `work_mode`/`posted_date` pass through, `is_india`/`is_remote` computed in the scraper.

## Tasks

### Phase 2a: backend (each item: minimal, backwards compatible, tested, listed in the PR)
- [x] `config.py` (pydantic-settings): `DATABASE_URL`, `SECRET_KEY`, `APP_ENV`, `CORS_ORIGINS`, `INGEST_TOKEN`, `ADMIN_EMAIL/PASSWORD`, SMTP, alert settings, `ROOT_PATH`. Refuse to start with a missing/default `SECRET_KEY` unless `APP_ENV=dev`.
- [x] Pin `requirements.txt` to verified versions; add `werkzeug`, `itsdangerous`, `email-validator`; add `requirements-dev.txt`.
- [x] Migration 2: fix drift (drop `year_grad`, `grad_year` NOT NULL, non-unique password-hash index, `branch` nullable). Migration 3: `source`, `external_id`, `source_content_hash`, `is_remote`, `is_india`, `work_mode`, `posted_date`, `last_seen_at`, `updated_at`, `students.alerts_enabled`; unique `(source, external_id)`.
- [x] Ingest: token auth, per-record results, length validation, upsert, bump `last_seen_at`.
- [x] Admin bootstrap command (`python -m cli bootstrap-admin`) from `ADMIN_EMAIL`/`ADMIN_PASSWORD`, run at container start; `deactivate-stale` command.
- [x] Auth on `/company`, `/companies`, `/jobs/{id}` (README says so; needs teammate confirmation).
- [x] `/me/matches`: hide 0% matches unless `include_unmatched=true` (TC-37).
- [x] `/jobs`: validated pagination (422 for `limit<1`/`offset<0`, `limit>100` clamps per TC-30), filters `location`, `skill`, `grad_year`, `source`, `scope`, `sort`, `X-Total-Count` header; `JobOut` gains company name and freshness fields.
- [x] Input hardening: password length, grad-year range, `branch` optional without 500, CORS from env.
- [x] Email alerts: opt-in flag, digest of new matches, SMTP via env (Mailpit in dev), `POST /internal/alerts/run`, sets `matches.notified_at`.
- [x] Analytics (SQL aggregations): skills demand/trend, skill gap (demand vs cohort skills), company/hiring patterns, curriculum alignment from `backend/curriculum.yaml`.
- [x] `/metrics` (prometheus-client), DB-aware `/health`.
- [x] Backend tests (pytest, real Postgres): all 42 `testcases.md` cases + ingest/upsert/token/auth/alerts/analytics.

### Phase 2b: scraper
- [x] Fix Internshala employer (selector `company_name`; return `company`); re-run, report new dedup numbers.
- [x] Mapper + ingest client (batches, retries, per-record result handling), truncation/normalisation, India/remote flags.
- [x] CLI `scraper run --push`; `scraper serve` (scheduler + `/metrics` + `/health`).
- [x] Rename Ollama setting to `OLLAMA_HOST` (keep `OLLAMA_URL` as an alias), default `http://host.docker.internal:11434`.
- [x] Metrics: pages scraped, extraction ok/fail, LLM latency, run duration, records pushed/rejected.
- [x] Non-root, healthchecked image. Integration test: fixture markdown → mocked Ollama → backend ingest → queryable via API.

### Phase 3: frontend (React + Vite + TS)
- [x] Auth pages, listings (search, filters, sort, pagination, freshness, scope India+remote default), job detail + apply link, matches, alert subscription/profile, 4 analytics pages, loading/empty/error states, API base from config, multi-stage Dockerfile → nginx, lint + typecheck + unit tests.

### Phase 4: infrastructure
- [x] `docker-compose.yml`: db, backend, scraper, frontend, nginx, prometheus, grafana, mailpit; healthchecks, `service_healthy` ordering, named volumes, restart policies, env-only credentials, `extra_hosts` for host Ollama/Firecrawl.
- [x] nginx: `/`→frontend, `/api/`→backend, `/grafana/`→grafana; gzip, timeouts, security headers.
- [x] Prometheus scrape configs; Grafana datasource + dashboards (API health, scraper pipeline) provisioned from files.

### Phase 5: CI/CD
- [x] `ci.yml`: lint, typecheck, unit tests, `alembic upgrade head` + `alembic check` on Postgres, image builds, compose smoke test with mocked Ollama/Firecrawl.
- [x] `release.yml` to GHCR (sha / latest / semver, cache, OCI labels); `docker-compose.prod.yml`; actionlint clean.

### Phase 6: hardening + docs
- [x] `.gitattributes` (LF), non-root images, README (Mermaid, setup, env reference, troubleshooting), final AUDIT/PLAN/DECISIONS update, Known limitations, evidence, PR.

## Assumptions
- Postgres 16; Python 3.12; Node 20 LTS.
- Real Ollama/Firecrawl run on the host, never in CI. Only the host's `qwen2.5vl:7b` is installed locally, so end-to-end extraction runs use that or are skipped; tests mock Ollama.
- The remote `main` is protected by convention: nothing is pushed to it. All work stays on `integration/full-stack`.
