# Mission: integrate and finish the off-campus opportunity aggregation platform end to end

You are the integration and delivery engineer for a 5-person DevOps course project. The backend
was written by a teammate and already lives in this GitHub repository. The scraper + Ollama
extraction module has been built separately. Your job: understand what exists, integrate
everything, build what is missing, and deliver a system that runs with one command and is
built, tested and published by CI. Work autonomously, but follow the phases and rules below.

## Project intent (verify against the code; the code wins if they differ)
Scrape company career pages (Microsoft careers first, more sources later) with Firecrawl,
extract structured listings with a locally hosted Ollama model, and serve them to students.
Planned features: structured listings, dedup + freshness tracking, eligibility match score,
automatic email alerts, skill-gap trend report for the placement cell, company / hiring
pattern analytics, curriculum-vs-industry alignment snapshot.

## Hard rules
1. Never push to main/master and never force-push. Work on branch `integration/full-stack`,
   commit in small logical commits (Conventional Commits), push the branch, and open a PR with
   `gh pr create` when done.
2. The backend is the source of truth. Adapt the scraper and frontend to its existing API,
   models and conventions. Change backend code only to fix a real bug or add something the
   integration genuinely needs. Every backend change must be minimal, backwards compatible,
   tested, and listed in the PR under "Backend changes", with the reason.
3. Never commit secrets. All config comes from env vars; provide `.env.example` with every
   variable documented. Add `.env` to `.gitignore` if it's not there.
4. Do not claim something works unless you ran it and saw it work. "Should work" is not done.
5. Ask me only when you are truly blocked: a missing secret, a decision only the team can make,
   or contradictory requirements. Otherwise make the reasonable choice, record it in
   `docs/DECISIONS.md`, and continue.
6. Do not delete or rewrite teammates' work wholesale. Refactor only where integration needs it.

## Phase 0: Discovery (read-only; no code changes yet)
- Map the repository: languages, frameworks, entry points, dependency files, existing Docker
  or CI config, tests, README / docs, branch and commit history (`git log --oneline -50`).
- Understand the backend in depth: every route (method, path, request and response schema,
  auth), data models and DB schema, migrations, how listings are expected to arrive (an
  ingest endpoint? direct DB writes? a queue?), background jobs, email-alert mechanism,
  config / env vars, and how to run its tests.
- Locate the scraper + Ollama module (in this repo or a path I give you) and understand its
  output schema.
- Run what exists: install deps, run the backend locally, run its test suite. Record
  everything that fails.
- Write `docs/AUDIT.md` with: architecture as found, API contract table, data flow, what is
  done / partial / missing per feature, every bug or risk found (file:line), and the gaps
  between the scraper's output schema and the backend's expected input.
- Stop and show me a short summary of AUDIT.md plus your plan (Phase 1) before writing code.

## Phase 1: Plan
Write `docs/PLAN.md`: ordered tasks per phase below, the integration contract you will use
between scraper and backend, the frontend stack choice (reuse whatever exists; if nothing
exists, use React + Vite + TypeScript), and any assumptions. Keep a task list and update it
as you go.

## Phase 2: Scraper ↔ backend integration
- Put the scraper in a clear location (e.g. `services/scraper/`), keeping its tests passing.
- Connect its output to the backend through the backend's own mechanism (ingest API
  preferred; otherwise the backend's data-access layer). Map fields explicitly; handle
  missing / null fields; keep (source, external_id) as the dedup key and content_hash for
  freshness.
- The scraper must reach Ollama via `OLLAMA_HOST` and Firecrawl via `FIRECRAWL_API_URL`
  (+ optional `FIRECRAWL_API_KEY`). Locally on Docker Desktop, Ollama runs on the host:
  default to `http://host.docker.internal:11434` and add
  `extra_hosts: ["host.docker.internal:host-gateway"]` so it also works on Linux.
- Add a way to trigger scraping (a CLI command plus a scheduled run: a cron container or
  the backend's scheduler, whichever fits the existing design).
- Add an integration test: fixture markdown → mocked Ollama → backend ingest → record is
  queryable through the API.

## Phase 3: Frontend
Build a complete, responsive frontend against the real backend API (no mock data in the
final build):
- Listings page with search, filters (type, location, work mode, graduation year, skills,
  source), sorting, pagination, freshness indicators.
- Listing detail page with an apply link to the original posting.
- Eligibility / match score view and email-alert subscription, if the backend supports them.
- Analytics pages (skill-gap trends, company / hiring patterns, curriculum alignment) for
  whatever the backend exposes; for anything not exposed, list it in the PR as a gap rather
  than faking it.
- Loading, empty and error states everywhere. API base URL from config; served behind nginx
  at `/`, API at `/api`.
- Production build in a multi-stage Dockerfile (build → nginx or static serve).

## Phase 4: Infrastructure
- Root `docker-compose.yml` bringing up: backend, database (and cache / queue if the backend
  needs them), scraper, frontend, nginx, Prometheus, Grafana.
  Firecrawl and Ollama are external dependencies configured by env vars; document how to run
  them, and do not embed the full Firecrawl stack in this compose file.
- Healthchecks on every service; `depends_on` with `condition: service_healthy`; named
  volumes for DB, Prometheus and Grafana data; restart policies; no hardcoded credentials.
- nginx as the single entry point: `/` → frontend, `/api/` → backend, `/grafana/` → Grafana
  (configure Grafana's root_url / serve_from_sub_path accordingly). Sensible timeouts, gzip,
  basic security headers.
- Prometheus: expose `/metrics` from the backend and the scraper using the standard client
  library for their language (requests, latency, errors; scraper: pages scraped, extraction
  successes / failures, LLM latency, run duration). Add scrape configs for them.
- Grafana: provisioned Prometheus datasource and at least one dashboard JSON (API health,
  scraper pipeline) loaded automatically from files, with no manual clicking.

## Phase 5: CI/CD (GitHub Actions + GHCR)
- `ci.yml` on pull requests and pushes: lint, type-check, unit tests for every service,
  build every Docker image, then a compose smoke test (bring the stack up with mocked Ollama
  / Firecrawl, wait for healthchecks, hit `/api` health and the frontend through nginx).
  Never require a real LLM in CI.
- `release.yml` on push to main and on version tags: build and push each image to
  `ghcr.io/<owner-lowercase>/<repo>-<service>` with tags `sha-<short>`, `latest` (main
  only) and the semver tag on tags. Use `docker/login-action` with `GITHUB_TOKEN`,
  `permissions: packages: write`, buildx with GitHub Actions cache, and OCI labels linking
  the image to the repo.
- Pin action versions; use dependency caching; give jobs clear names.
- Add `docker-compose.prod.yml` (or an override) that pulls the GHCR images instead of
  building locally.

## Phase 6: Error hunting and hardening
Systematically look for and fix:
- Contract mismatches (field names, types, date formats, enum values, nullability, pagination).
- CORS issues, wrong base URLs, nginx path / trailing-slash bugs.
- Container networking: services addressed by service name; host-only deps via
  host.docker.internal.
- Startup ordering, migrations not running, missing healthchecks, race conditions.
- Env vars used in code but missing from `.env.example` (and vice versa).
- Line-ending / path issues (the team develops on Windows): add `.gitattributes` forcing LF
  for shell scripts and Dockerfiles.
- Unpinned dependencies, images running as root where avoidable, large images (use slim
  bases and multi-stage builds).
- Unhandled exceptions in the scraper pipeline; one bad listing must never kill a run.

## Definition of done (verify each item by running it; paste evidence into the PR)
1. `cp .env.example .env` (filling only real secrets) then `docker compose up -d --build`
   brings every service to healthy.
2. `http://localhost/` shows the frontend with real data; `/api/...` responds; `/grafana/`
   loads with the provisioned dashboard showing live metrics; Prometheus targets all UP.
3. A scraper run with a small limit (e.g. 5 Microsoft postings) inserts records into the
   backend, and they appear in the frontend. A second run causes no duplicates.
4. All test suites pass locally; CI is green on the PR.
5. The release workflow is valid (actionlint passes) and will push images to GHCR on merge.
6. `README.md` covers: architecture diagram (Mermaid), prerequisites (Docker, Ollama + model,
   Firecrawl), setup, run, test, deploy, env var reference, and troubleshooting.
7. `docs/AUDIT.md`, `docs/PLAN.md` and `docs/DECISIONS.md` are up to date. A final
   "Known limitations" section lists anything not completed and why. It should be empty
   or nearly empty.

When every item is verified, push the branch, open the PR with a thorough description
(summary, backend changes, how to run, evidence, known limitations), and report back to me