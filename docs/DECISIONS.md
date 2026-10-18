# Decisions

Choices made without a team decision, newest last. Each says what, why, and how to undo it.

## D1. This branch includes chay_branch's unmerged backend work
- **What:** `integration/full-stack` was created from `origin/main` and then had `origin/chay_branch` merged in (merge commit, no rebase).
- **Why:** `main` only has the DB skeleton (`db.py`, `models.py`, Alembic). The routes, schemas, matching logic and `testcases.md` exist only on `chay_branch`, which is not merged into `main`. Integration needs the real backend.
- **Consequence:** merging this PR also merges chay_branch's work. The PR description must say so.
- **Undo:** if chay_branch changes, merge its new commits into this branch the same way (no force-push).

## D2. Merge conflict resolutions
- `requirements.txt`: both sides listed the same packages and differed only by a trailing newline; main's version (with newline) was kept.
- `.gitignore`: chay_branch moved it to `backend/.gitignore`; the root file was kept (it now covers the whole repo, including `scraper/`) and `backend/.gitignore` is unchanged.

## D3. Firecrawl is not part of this repository
- A local `firecrawl/` clone is git-ignored. Firecrawl is an external dependency configured by `FIRECRAWL_API_URL` / `FIRECRAWL_API_KEY`.

## D4. Ingest contract (from the Phase 0 audit, approved)
- Add nullable `source` + `external_id` with a unique `(source, external_id)` constraint in a **new** Alembic migration; ingest upserts on it. Payloads without them keep the legacy `company|title|location` hash path.
- Ingest is per-record tolerant: the response lists accepted/rejected records with reasons and a bad record never 500s the batch. The backend validates field lengths; the scraper truncates and normalises before sending.
- **Request-shape errors stay 422** (missing `title`, bad date): `testcases.md` TC-23/TC-24 require it. Only size/semantic problems are per-record rejections.
- Backend `content_hash` stays the unique identity (`sha256(source|external_id)` for keyed jobs). The scraper's own content hash goes into a new `source_content_hash` column and drives `unchanged` vs `updated`.
- Internshala's company field must be the real employer (scraper fix); dedup numbers re-measured after the fix.

## D5. Migrations and dependencies
- Drift is fixed by a **new** migration; the shipped one is never edited. `requirements.txt` is pinned to verified versions with the missing packages added. CI runs `alembic upgrade head` and `alembic check` against Postgres.

## D6. Ingest authentication
- `X-Ingest-Token` header compared with `hmac.compare_digest`; admin cookie sessions keep working. An admin bootstrap command creates/updates the admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

## D7. Matches and public routes
- `/me/matches` hides 0% matches by default; `include_unmatched=true` shows them (TC-37 passes).
- `/company`, `/companies`, `/jobs/{id}` now require login, as the README says. **Needs the backend author's confirmation** (behaviour change; called out in the PR).

## D8. Extra features are built small
- Email alerts (opt-in, SMTP via env, Mailpit in dev), analytics / skill-gap (SQL aggregations), curriculum alignment (editable `backend/curriculum.yaml`).
- Analytics and curriculum endpoints expose cohort data, so the skill-gap and curriculum endpoints are admin-only; demand/company endpoints need login.

## D9. India scope
- Remote / WFH postings are kept and flagged (`is_remote`; `is_india` when a place is in India). The API default stays `scope=all` so legacy data and TC-25 are unchanged; the UI defaults to India + remote with a filter to change it.

## D10. Hardening choices
- `APP_ENV` defaults to **production**: the app refuses to start with a missing/default `SECRET_KEY` unless `APP_ENV=dev`. Local runs set `APP_ENV=dev` (documented).
- Pagination: `limit<1` or `offset<0` → 422; `limit>100` clamps to 100 (TC-30 requires 200, not 422).
- `students.branch` becomes nullable (the register schema already treats it as optional; today that path 500s).
- The scraper stays in `scraper/` (not moved to `services/`): it is already a self-contained module. The backend stays in `backend/`.
- Scraper `serve` mode (long-running, exposes `/metrics`) because Prometheus cannot scrape a one-shot CLI.
