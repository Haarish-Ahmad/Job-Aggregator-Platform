# Audit

> **Status (end of integration work).** Sections 1–10 below are the **Phase 0 audit as found**, kept unchanged as the record of what
> the code did *before* this branch. **[Resolution](#resolution-of-the-audit-findings)** says what happened to each finding and
> **[Known limitations](#known-limitations)** lists what is still not done and why. The README describes the system as it is now.

## Phase 0 audit (as found)

Date: 2026-10-18 · Branch: `integration/full-stack` (= `origin/main` + `origin/chay_branch`, see [DECISIONS.md](DECISIONS.md) D1)

Everything below was observed by running the code, not just reading it, unless it says "(read)". Test harness and
logs were kept outside the repo. Backend code was **not** modified.

## 1. Summary

| Area | State |
|---|---|
| Backend routes | 12 routes, logic is mostly sound: **41 of 42** cases in `backend/testcases.md` pass when the DB schema comes from the models |
| **Fresh install** | **Broken three ways**: unpinned deps pull a SQLAlchemy that can't talk to the listed driver; 3 imports are missing from `requirements.txt`; the Alembic migration disagrees with the models, so **registering any student returns 500** |
| Scraper → backend | **No integration exists.** The backend has no `source` / `external_id`, its dedup key would drop ~25% of today's real scraped postings, and ingest needs an admin *session cookie* that can only be created by editing the DB by hand |
| Alerts, analytics, metrics, scheduler, tests, CI, Docker for backend | **Not started** (backend has none of them) |
| Scraper | Works: 149 unit tests pass; 1,200+ India postings scraped today (see §7). No metrics, no ingest client, Ollama var named `OLLAMA_URL` (mission wants `OLLAMA_HOST`) |

Biggest risks for the plan: B1–B3 (fresh clone doesn't run), B4–B5 and H1–H3 (ingest contract), and that **the backend has no
automated tests**, only manual Bruno cases.

## 2. Repository as found

```
.
├── backend/            FastAPI + SQLAlchemy 2 + Alembic (from chay_branch; not yet in main)
│   ├── main.py         all routes (147 lines)      ├── matching.py  rule-based eligibility + skill score
│   ├── models.py       5 tables                    ├── schemas.py   Pydantic request/response models
│   ├── db.py           engine + get_db             ├── alembic/     1 migration
│   └── testcases.md    42 manual Bruno cases + README (README.md)
├── scraper/            Python 3.12 CLI, 7 adapters, Ollama extraction, JSONL storage, 149 unit tests, Dockerfile
├── requirements.txt    backend deps (root, unpinned, 6 packages)
├── mission.md · docs/  this audit, DECISIONS.md
└── firecrawl/          local clone of Firecrawl, git-ignored (external dependency)
```

No frontend, no root `docker-compose.yml`, no `.github/`, no backend Dockerfile, no nginx / Prometheus / Grafana config,
no backend tests, no linter/type-check config. `git log`: `main` = 8 commits (skeleton); `chay_branch` = 3 more (routes,
schemas, `testcases.md`); this branch adds the scraper and a merge.

## 3. Backend architecture

- **Stack:** FastAPI, SQLAlchemy 2 (sync), PostgreSQL via psycopg2, Alembic, Starlette `SessionMiddleware`
  (signed cookie), `werkzeug` password hashing.
- **Auth:** cookie session (`session=…`, HttpOnly, SameSite=Lax, 12 h). Roles: `student` (default) and `admin`.
  There is **no API to create an admin** (see B5).
- **Config:** only `SECRET_KEY` is read from the environment (`main.py:15`). The DB URL is hardcoded
  (`db.py:4`: `postgresql://jobs:jobs@localhost:5432/jobs`), so the backend cannot reach a `db` container as is.
- **Run:** `alembic upgrade head` then `uvicorn main:app` from `backend/` (imports are top-level: `from db import …`),
  so the working directory must be `backend/`.

### Data model (from `models.py`)

| Table | Columns of note |
|---|---|
| `students` | email (unique), password_hash, branch (NOT NULL), grad_year (NOT NULL), role, cgpa, skills[], resume_link |
| `company` | company_name (unique), careers_url, description |
| `job_postings` | company_id→company, title(255), description, location(150), job_type(30), min_cgpa, allowed_branches[], allowed_grads[], necessary_skills[], apply_url(500), **content_hash (unique)**, is_active, scraped_at, deadline_at |
| `matches` | (student_id, job_id) unique, score, `notified_at` (never written) |
| `scrapes` | started_at, scrap_status, jobs_found (**no code uses this table**) |

### API contract (as implemented)

| Method | Path | Auth in code | Auth in README | Request → response |
|---|---|---|---|---|
| GET | `/health` | none | none | → `{"status":"ok"}` (no DB check) |
| POST | `/auth/register` | none | none | `StudentDetails` → 201 `StudentOut`; 409 duplicate email |
| POST | `/auth/login` | none | none | `{email,password}` → `StudentOut` + cookie; 401 |
| POST | `/auth/logout` | none | login | → `{"detail":"logged out"}` |
| GET | `/me` | session | login | → `StudentOut` |
| PATCH | `/me/update` | session | login | `StudentUpdate` (branch, cgpa 0–10, grad_year, skills, resume_link) → `StudentOut` |
| GET | `/me/matches?min_score=` | session | login | → `[{score, job: JobOut}]`; **also writes `matches` rows** |
| POST | `/company` | **none** | login | `{company_name, careers_url, description?}` → 201 `CompanyOut`; 409 |
| GET | `/companies` | **none** | login | → `[CompanyOut]` (no pagination) |
| POST | `/internal/jobs` | session + `role=admin` | admin | `{jobs:[jobsIn]}` → `{inserted, skipped}` |
| GET | `/jobs?q&company_id&job_type&active_only&limit&offset` | session | login | → `[JobOut]` (limit capped at 100; no total count, no sort option, no location/skill/graduation-year/source filters) |
| GET | `/jobs/{id}` | **none** | login | → `JobOut`; 404 |

`jobsIn` (ingest): `company_name`, `title`, `apply_url` required; `location`, `job_type`, `description`, `min_cgpa`,
`allowed_branches[]`, `allowed_grads[]`, `required_skills[]`, `deadline` optional. `JobOut` has **no company name**
(only `company_id`) and no `scraped_at`, so a UI cannot show a company or freshness without extra calls.

### Data flow (intended vs actual)

```mermaid
flowchart LR
  S[Scraper CLI] -- "JSONL files (today)" --> F[(data/jobs.jsonl)]
  S -. "POST /internal/jobs (missing)" .-> B[Backend]
  B --> DB[(Postgres)]
  Student -- "cookie session" --> B
```

Today the scraper writes only local JSONL; nothing sends data to the backend.

## 4. Feature status

| Feature (mission) | Status | Evidence |
|---|---|---|
| Structured listings | **Partial** | `job_postings` + `/jobs`; lacks source, external id, work mode, multiple locations, posted date, company on `JobOut` |
| Dedup + freshness | **Partial / flawed** | hash dedup exists but is too coarse (I2); `is_active` and `scraped_at` are never updated after insert; expired postings still listed |
| Eligibility match score | **Done** (rule-based) | `matching.py`; TC-34–TC-36 pass, TC-37 differs (see §6) |
| Email alerts | **Missing** | only an unused `matches.notified_at` column; no mailer, scheduler or SMTP config |
| Skill-gap trend report | **Missing** | no endpoint or model |
| Company / hiring analytics | **Missing** | no endpoint |
| Curriculum-vs-industry alignment | **Missing** | no endpoint or curriculum data |
| Admin / ingest access | **Partial** | route exists; no way to obtain an admin (B5) |
| Scheduled scraping | **Missing** | scraper is a one-shot CLI |
| Metrics / health depth | **Missing** | `/metrics` → 404; `/health` doesn't check the DB |

## 5. Bugs and risks

Severity: **Blocker** = system doesn't work from a clean clone · **High** = wrong data or security · **Medium/Low** = hardening.

### Blockers (fresh clone)
| # | Where | Problem | Evidence |
|---|---|---|---|
| B1 | `requirements.txt` (all lines unpinned) | `pip install -r` now pulls SQLAlchemy 2.1.5, whose default `postgresql://` driver is psycopg v3; only `psycopg2-binary` is listed → `ModuleNotFoundError: psycopg` at import and at `alembic upgrade` | reproduced; works with `sqlalchemy<2.1` |
| B2 | `requirements.txt` | Missing packages the code imports: `werkzeug` (`main.py:7`), `itsdangerous` (SessionMiddleware), `email-validator` (`EmailStr`, `schemas.py:1`) | each caused a failed import |
| B3 | `alembic/versions/ab7b8208ab2d…` vs `models.py` | Migration was generated before the model was changed (commit "update database model constraints"). It creates `students.year_grad` (line 45) and `job_postings.year_grad` (line 66) as NOT NULL with no default, which no model or route fills; `students.grad_year` is nullable in the DB but NOT NULL in the model; `ix_students_password_hash` is unique in the DB but not in the model. **`POST /auth/register` returns 500** (`NotNullViolation … year_grad`) on a migrated DB. `alembic check` fails. | reproduced |

### Integration blockers
| # | Where | Problem |
|---|---|---|
| B4 | `db.py:4` | DB URL hardcoded to `localhost`; unusable in Docker without editing code. Needs `DATABASE_URL` env var (backward-compatible default). |
| B5 | `main.py:90–92`, `routes` | Ingest requires a logged-in **admin session**. Nothing creates an admin: register ignores `role`, PATCH ignores `role`, and the spec says to run `UPDATE students SET role='admin'` by hand. A scraper container cannot do that. |

### High
| # | Where | Problem |
|---|---|---|
| H1 | `main.py:31–33`, `101` | Dedup key = `company|title|location`. Different postings with the same title and city collapse into one; the first stored version wins forever, so **updated postings are never refreshed** (re-sent changed description: `skipped`, stored description unchanged). Also weak normalisation: `' bengaluru '` vs `'bengaluru'` creates a duplicate. |
| H2 | `main.py:89–118` | One bad row aborts the **whole batch**: a location over 150 chars → HTTP 500, nothing saved (even valid rows in the same request). Same for any over-length `title` / `job_type` / `apply_url`. |
| H3 | `main.py:97` | A new company is created with `careers_url = apply_url` of its first job (a job link, not a careers page). |
| H4 | `models.py:12`, `schemas.py:17` | `branch` is optional in the register schema but NOT NULL in the model → registering without a branch returns **500** instead of 422. |
| H5 | `main.py:15`, `16` | Default `SECRET_KEY="dev-secret-change-me"` is used silently if unset; `https_only=False`. Anyone who knows the default can forge an admin session cookie. |
| H6 | `main.py:18` | CORS allows only `http://localhost:5173`. Behind nginx at `http://localhost/` the browser origin differs; credentialed requests will be blocked unless same-origin via `/api`. |
| H7 | `main.py:39–51` | `POST /company`, `GET /companies`, `GET /jobs/{id}` are public although the README (and `get_current_user` elsewhere) say login is required. Anyone can create companies. |
| H8 | `schemas.py:19`, `main.py:55–62` | No password or grad-year validation: empty password (`""`) and `grad_year=1800` are accepted with 201. |

### Medium / Low
| # | Where | Problem |
|---|---|---|
| M1 | `main.py:131` | `limit=-1` → 500; `offset=-1` → connection error. The spec notes the clamp should be `max(1, min(limit,100))`; `limit=0` returns `[]`. |
| M2 | `main.py:141–146` | A `GET` writes to the DB (`save_matches`) and recomputes in Python over **all** active jobs on every call; no pagination on matches. |
| M3 | `main.py:124` | `q` is used in `ILIKE` without escaping `%` / `_`; `q=%` matches everything. |
| M4 | `main.py:95–115` | Per-item queries inside the loop (N+1) and a read-then-insert race: concurrent ingests can hit the unique `content_hash` and fail the whole batch. |
| M5 | `matching.py:6–15` | Eligibility never checks `is_active` for `/jobs/{id}`; expired jobs remain in `/jobs` (`active_only` only checks the flag, which nothing ever clears). |
| M6 | `schemas.py:56–61` | `allowed_branches` and `required_skills` share one lowercasing validator; `allowed_branches` is stored lowercase (harmless today because matching lowercases, but `JobOut` shows `["cse","it"]`). |
| M7 | `main.py:77–87` | `PATCH /me/update` silently ignores unknown fields (e.g. `role`, `email`) with 200, as the spec documents. Acceptable, but a client typo is invisible. |
| M8 | `models.py:65` | `scrapes` table is defined and migrated but never used (no run history to power the "scraper pipeline" dashboard). |
| M9 | root | No `.gitattributes` (team is on Windows), no backend Dockerfile, no tests, no linter / type checker, nothing pinned. |

## 6. `backend/testcases.md` vs actual behaviour

Method: a script ran TC-01…TC-42 in order against a live server (DB built with `Base.metadata.create_all`, i.e. the
models; promoting Asha to admin via SQL as the spec instructs).

**Result: 41/42 pass.** Mismatches and documentation drift:

| # | Spec says | Actual | Verdict |
|---|---|---|---|
| TC-37 | Ravi's matches: only *ECE Only* and *Open Role* | also *Half Match* with score **0.0**: `is_eligible` doesn't require any skill overlap and the job has no branch/CGPA limit | **Mismatch**: either the spec is wrong or the route should filter zero-score jobs (needs the team's decision) |
| TC-03 | 201 | **500** on a DB built by `alembic upgrade head` (`year_grad` NOT NULL). TC-04…TC-42 all need a registered user, so I did not run them on that schema | B3 |
| TC-19, TC-17, TC-18 | "Before: Logged in" | work without login | H7 (README + spec expect auth, code has none) |
| TC-30 | clamp to 100 | passes; the "Issues found" note's `max(1,…)` guard is **not implemented** | M1 |
| TC-14 / TC-15 | 200, no change | pass; spec suggests `extra="forbid"` → 422 (not implemented) | M7 |
| README table | `/company`, `/companies`, `/jobs/{id}` need login | no auth in code | H7 |
| "Issues found" #4 | "There is no `year_grad` column on jobs" | the migration **creates** `job_postings.year_grad` NOT NULL | B3 |
| Spec gap | no case covers: unauthenticated `/company`, over-long fields, invalid pagination, register without branch, empty password, dedup of changed content | the failures above (H2, H4, H7, H8, M1, H1) were found only by the extra probes | untested |

## 7. Scraper ↔ backend: gaps

Scraper output is `JobRecord` (`scraper/src/scraper/models.py`). Real data measured from today's India run:
internshala 777, shine 299, unstop 134, greenhouse 5, microsoft 3, google 1.

| Scraper field | Backend field | Gap |
|---|---|---|
| `company` | `company_name` | Direct. But Internshala's company is always the literal **"Internshala"** (cards give no employer name) |
| `title` | `title` | Direct (none >255 in sample) |
| `url` | `apply_url` | Direct; also the only stable identity |
| `locations: list[str]` | `location: str (≤150)` | Must join; 5 Internshala records exceed 150 chars and would fail the whole batch (H2) |
| `employment_type` (`internship`/`full_time`/`part_time`/`contract`/`unknown`) | `job_type` | Free string ≤30 → pass-through works |
| `description_text` | `description` | Direct |
| `extraction.data.skills` | `required_skills` | Only present when `--extract` was run; else empty (or `required_qualifications` as a rough substitute) |
| `extraction.data.graduation_years` | `allowed_grads` | Direct when extracted |
| `min_experience_years` | none | No column |
| `posted_date` | none (only server `scraped_at`) | No column; freshness can't use the source's date |
| `work_mode`, `department`, `salary_*`, `degree_required` | none | No columns |
| `source` + `external_id` | none | **Dedup key in the mission, but the backend has neither** |
| `content_hash` | `content_hash` (unique) | **Different meaning**: the backend overwrites it with its own `company|title|location` hash |

Consequences measured on real data (backend hash vs scraper `(source, external_id)`):

| Source | Real postings | Distinct backend keys | Would be lost as "duplicates" |
|---|---|---|---|
| internshala | 777 | 467 | **310 (40%)** |
| shine | 299 | 269 | 30 (10%) |
| unstop | 134 | 131 | 3 |
| others | 9 | 9 | 0 |

So the existing ingest contract cannot carry the scraper's data faithfully. This is the central design question for
Phase 1 (see §9). Other scraper findings:

- Ollama is configured as `OLLAMA_URL` (`scraper/src/scraper/config.py:34`); the mission wants `OLLAMA_HOST`. Firecrawl vars already match.
- No `/metrics`, no ingest client, no scheduler, `Dockerfile` has no healthcheck / non-root user.
- Scraper can't run in Docker today against host Ollama (no `extra_hosts`).
- The India-only requirement is enforced at *discovery* by `--location India`; **Internshala (424) and Unstop (52) still store work-from-home postings with no India place** (476 of 1,219 records). A downstream filter is needed.
- Unit tests: **149 pass** (`pytest`), one integration test deselected.

## 8. Run log (what I ran)

| Step | Result |
|---|---|
| `pip install -r requirements.txt` (clean venv) | installs, but app can't start (B1) |
| `import main` | fails: `psycopg`, then `itsdangerous`, `werkzeug`, `email-validator` (B1, B2) |
| `alembic upgrade head` (Postgres 16 in Docker) | succeeds once SQLAlchemy < 2.1 |
| `alembic check` | **fails**: drift between migration and models (B3) |
| `POST /auth/register` on migrated DB | **500** (`year_grad` NOT NULL) |
| TC-01…42 on models-built DB | 41 pass, TC-37 differs |
| Extra probes | H1, H2, H4, H7, H8, M1, M3, CORS, cookie flags, `/metrics` 404 |
| Scraper `pytest` | 149 passed |

## 9. Open questions for you (answers change the plan)

These need a team decision, not just engineering (mission rule 5):

1. **Ingest contract.** The mission wants `(source, external_id)` as the dedup key and `content_hash` for freshness. The backend has neither, and its current key loses up to 40% of Internshala data. Minimal backwards-compatible change: add nullable `source`, `external_id` columns (unique together when present) via a **new** Alembic migration, accept them as optional fields on `jobsIn`, and upsert by them while keeping the old hash path for payloads without them. Is that acceptable as a "backend change the integration genuinely needs"?
2. **Migration drift (B3).** Fix by adding a new migration that brings the DB to the models (drops `year_grad`, fixes nullability/index) rather than editing the existing one? (Recommended: never rewrite a shipped migration.)
3. **Service account for ingest (B5).** Prefer a static ingest token header (`INGEST_TOKEN` env var, checked only on `/internal/jobs`) over a cookie session for the scraper? A minimal, backwards-compatible addition; admin-by-session would still work.
4. **TC-37.** Should students see jobs with a 0% skill match? Spec says no; code says yes.
5. **Public routes (H7).** README says login is required for `/company`, `/companies`, `/jobs/{id}`; code allows anonymous access. Which is intended? (Fixing it is a behaviour change.)
6. **Scope of missing features.** Email alerts, skill-gap, hiring analytics and curriculum alignment have no backend at all. The mission says to list gaps rather than fake them; should I build minimal backends for them (new endpoints under `/api/analytics/…`, SMTP-optional mailer) or leave them as documented gaps?
7. **India-only.** Should the platform drop WFH / no-location postings during ingest (strict India-only), or keep them flagged remote?

## 10. Known limitations of this audit

- Frontend, nginx, Prometheus, Grafana, CI: nothing exists to audit.
- psycopg-vs-psycopg2 behaviour was verified with SQLAlchemy 2.0.55 (works) and 2.1.5 (fails); other drivers weren't tried.
- Concurrency (M4) is read from the code, not load-tested.
- The 42 cases were run by script, not through Bruno; request bodies are copied from `testcases.md`.


---

## Resolution of the audit findings

Evidence for every "fixed" row is an automated test (backend 158, scraper 222, integration 9, frontend 63) and the whole-stack
smoke test (`scripts/smoke.sh`, also run by CI). IDs are those used in section 5.

| ID | Finding | Status | How |
|---|---|---|---|
| B1 | Unpinned deps; SQLAlchemy 2.1 breaks psycopg2 | **Fixed** | `requirements.txt` pinned (SQLAlchemy `2.0.55`), `requirements-dev.txt` |
| B2 | `werkzeug`, `itsdangerous`, `email-validator` missing | **Fixed** | added and pinned |
| B3 | Migration drifted from models; register returned 500 | **Fixed** | new migration `7c1e4a90b2d3` (data-preserving, tested against the original schema); the shipped migration is untouched; CI runs `alembic upgrade head` + `alembic check` |
| B4 | DB URL hardcoded | **Fixed** | `DATABASE_URL` env (`backend/config.py`) |
| B5 | No way to create an admin / machine ingest | **Fixed** | `X-Ingest-Token` (constant-time compare) + `python cli.py bootstrap-admin` from `ADMIN_EMAIL`/`ADMIN_PASSWORD` |
| H1 | Coarse dedup key lost postings; never refreshed | **Fixed for scraped data** | upsert on `(source, external_id)` with a fingerprint; Internshala 310 of 777 lost → 0. Payloads *without* a source still use the old key (backward compatible) |
| H2 | One bad record 500s the batch | **Fixed** | per-record validation and savepoints; results list per record |
| H3 | `careers_url` was a job link | **Fixed** | the posting's site origin |
| H4 | Register without `branch` returned 500 | **Fixed** | `branch` nullable (migration) |
| H5 | Default `SECRET_KEY` | **Fixed** | refuses to start unless `APP_ENV=dev` or a private key is set |
| H6 | CORS only `localhost:5173` | **Fixed** | `CORS_ORIGINS` env; the bundled nginx makes app and API same-origin |
| H7 | `/company`, `/companies`, `/jobs/{id}` public | **Fixed, needs confirmation** | now require login, as the documentation said. **Behaviour change: the backend author must confirm** |
| H8 | Empty password / year 1800 accepted | **Fixed** | password ≥ 8, grad year 2000–2100, cgpa 0–10 |
| M1 | `limit=-1` 500 | **Fixed** | `limit<1`, `offset<0` → 422; `limit>100` clamps (TC-30) |
| M2 | `GET /me/matches` writes to the DB | **Open** | needed for alerts; see limitations |
| M3 | `%` / `_` not escaped in search | **Fixed** | escaped |
| M4 | N+1 queries / ingest race | **Race fixed, N+1 open** | savepoint + unique-violation handling; per-record queries remain (batches ≤ 500) |
| M5 | Expired / vanished postings stay listed | **Fixed** | `hide_expired`, `last_seen_at`, `deactivate-stale` after each scrape cycle. Expired postings are still *listed by default* because TC-25 requires it |
| M6 | `allowed_branches` lowercased | **Open (harmless)** | matching is case-insensitive; the UI upper-cases for display |
| M7 | PATCH silently ignores unknown fields | **Open (documented)** | TC-14/15 specify this |
| M8 | `scrapes` table unused | **Open** | run history lives in Prometheus metrics instead |
| M9 | No `.gitattributes`, Dockerfile, tests, linter | **Fixed** | all added; CI enforces them |
| TC-37 | 0%-match jobs shown | **Fixed** | hidden unless `include_unmatched=true` |
| Gaps | Email alerts, analytics, skill gap, curriculum, metrics, scheduler | **Built** | see README; each has tests |
| Scraper | `OLLAMA_URL` name; no metrics, no ingest client, no scheduler, root image | **Fixed** | `OLLAMA_HOST` (old name still read), `scraper serve`, `--push`, metrics, non-root healthchecked image |
| Scraper | WFH/no-location postings stored | **Handled** | flagged `is_remote` / `is_india`; the UI defaults to India + remote with a filter |

### Defects found *after* the audit, while verifying on live data
These were not in the audit; each has a regression test.

* Shine: the employer was sometimes the "Actively Hiring" badge (21 of the first 100 live jobs). Fixed in `parse_listing`.
* Google: `normalize()` read the employer brand and dropped it (same bug class as Internshala).
* The scraper pushed *cached* records for unchanged jobs, so parser fixes never reached the backend, and its change fingerprint
  covered only the description text, so extraction enabled later was never delivered. Both fixed (see DECISIONS D11).
* Dates: a deadline of "today" showed as "Closes tomorrow", and a posted date was off by one day in far-east time zones.
* `bootstrap-admin` accepted an `ADMIN_EMAIL` the login form would reject (e.g. `admin@example.test`), creating an admin who could never sign in.
* The first smoke test could not bind its mock ports (a real Firecrawl owned them) and silently scraped the real site; the test
  now uses its own ports and aborts if the mocks are not up.

## Known limitations

Things not done, and why. None blocks the stack from running.

**Needs a decision or action from the team**
* **This branch contains `chay_branch`, which is not merged into `main`.** Merging this PR merges that backend work too (DECISIONS D1).
* **Login is now required on `/company`, `/companies`, `/jobs/{id}`** (H7). The backend author should confirm this is intended.
* **The release workflow has not published anything yet.** It is validated with `actionlint` and its build steps run in CI without
  pushing, but the push to GHCR only happens on merge to `main` or a version tag. After the first release, check that the packages'
  visibility suits you (new GHCR packages are private by default).

**External services (by design)**
* Firecrawl and Ollama are not in the compose file. Shine needs Firecrawl; without it that source logs a warning and is skipped.
  Ollama extraction is off by default (`SERVE_EXTRACT=false`); on Linux the host's Ollama must listen on `0.0.0.0` for containers to reach it.
* Without extraction, skills come from each source's own skill tags. Microsoft, Google and Greenhouse list requirement *sentences*
  rather than skills, so those postings carry no skills (and add nothing to the skill and curriculum analytics) until extraction runs.

**Product scope**
* Only India-based fresher/intern software roles survive the relevance filter, so some sources yield very little: for example Microsoft
  produced **1 qualifying posting** in the verification run (5 were discovered, 4 filtered), Google 1, Y Combinator 0, Greenhouse 5.
  Most of the data comes from Unstop, Shine and Internshala.
* Internshala listings carry only card text (its detail pages are disallowed by robots.txt) and Shine gives only relative posting
  times, so those sources have short or missing descriptions / no posted date.
* Indeed, Naukri and Glassdoor are not covered: they sit behind CAPTCHAs / bot walls. The terms of service of the covered sites were not reviewed.
* No password reset, email verification, or per-email unsubscribe link (alerts are switched off in the profile). Sign-in is rate-limited by nginx only.
* Alerts are one digest per student after each scrape cycle; Prometheus alert rules exist but no Alertmanager is bundled.

**Scale and engineering**
* `GET /me/matches` recomputes in Python over all active jobs and writes the result; fine for thousands of postings, not millions (M2).
* Ingest does per-record lookups (batches are capped at 500) (M4).
* The backend runs as a single process: the Prometheus client keeps counters in memory, so more workers would split the numbers.
* Counters for a scrape started by hand (`docker compose exec scraper scraper run …`) are not visible in Prometheus; only the scheduled cycles of `serve` are.
* The first scrape after upgrading from the old fingerprint reports every existing job as `updated` once.
* Frontend tests are component-level; there is no browser end-to-end test in CI. The pages were checked manually in headless Chrome against live data.
* Legacy ingest payloads without `source`/`external_id` still collapse same-title/same-city postings (kept for backward compatibility).
