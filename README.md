# Job Aggregator Platform

Off-campus jobs and internships for students. The platform **scrapes** job boards and company career pages
(with Firecrawl), optionally **extracts** structured fields with a locally hosted LLM (Ollama), stores the listings,
**matches** them to each student's profile, **emails** alerts, and gives the placement cell **analytics**
(skills in demand, skill gap, hiring patterns, curriculum alignment).

One command starts everything: `docker compose up -d --build`.

## Screenshots

Taken from the running stack with live data (not mock-ups).

| Jobs (desktop) | Jobs (phone) |
|---|---|
| ![Jobs list with filters, skills and freshness badges](docs/screenshots/listings.png) | ![Jobs list on a phone, filters collapsed](docs/screenshots/mobile.png) |

| Skills in demand | Job detail |
|---|---|
| ![Most requested skills](docs/screenshots/analytics.png) | ![Job detail with apply link](docs/screenshots/detail.png) |

| Grafana: API health | Grafana: scraper pipeline |
|---|---|
| ![API health dashboard](docs/screenshots/grafana-api.png) | ![Scraper pipeline dashboard](docs/screenshots/grafana-scraper.png) |

## Architecture

```mermaid
flowchart LR
  subgraph External["Run outside this repo's compose (see Prerequisites)"]
    FC[Firecrawl :3002]
    OL[Ollama :11434]
  end
  subgraph Sites["Job sites"]
    S1[Shine / Internshala / Unstop<br/>Greenhouse / Microsoft / Google / YC]
  end
  Browser((Browser)) -->|"/  /api  /grafana"| NGX[nginx<br/>single entry point]
  NGX -->|/| FE[frontend<br/>React + nginx]
  NGX -->|/api/| BE[backend<br/>FastAPI]
  NGX -->|/grafana/| GF[Grafana]
  SC[scraper<br/>serve mode] -->|render pages| FC
  SC -->|extract skills| OL
  SC -->|scrape| S1
  SC -->|"POST /internal/jobs<br/>X-Ingest-Token"| BE
  BE --> DB[(PostgreSQL)]
  BE -->|SMTP alerts| MP[Mailpit<br/>dev inbox]
  PR[Prometheus] -->|/metrics| BE
  PR -->|/metrics| SC
  GF --> PR
```

| Service | What it is | Port (host) |
|---|---|---|
| `nginx` | Single entry point: `/` app, `/api/` API, `/grafana/` dashboards | `80` (`HTTP_PORT`) |
| `frontend` | React + Vite + TypeScript app served by an unprivileged nginx | internal |
| `backend` | FastAPI + SQLAlchemy + Alembic; runs migrations and the admin bootstrap on start | internal |
| `db` | PostgreSQL 16 (named volume `pgdata`) | internal |
| `scraper` | `scraper serve`: scheduled scrape, push to the backend, `/metrics`, `/health` | internal |
| `prometheus` | Scrapes backend and scraper; alert rules | `127.0.0.1:9090` |
| `grafana` | Datasource and two dashboards provisioned from files | via `/grafana/` |
| `mailpit` | Catches alert emails in development | `127.0.0.1:8025` |

### How data flows

1. The **scraper** discovers postings on each source, fetches and normalises them, and optionally extracts skills with Ollama.
2. Every processed job is sent to `POST /internal/jobs` (header `X-Ingest-Token`). The backend upserts on `(source, external_id)`:
   `inserted`, `updated` (content changed), `unchanged` (re-seen: `last_seen_at` is refreshed) or `rejected` with a reason.
   One bad record never fails the batch. Every run re-sends everything it saw, so a failed push heals itself on the next run.
3. Postings not seen for `STALE_DAYS` are marked inactive after each cycle.
4. Students see listings, matches and analytics in the **frontend**; alert emails go out after each cycle to students who opted in.

## Prerequisites

* **Docker** with Compose v2.24 or newer (`docker compose version`).
* **Firecrawl** (needed for Shine, whose pages only exist after JavaScript runs; other sources work without it).
  Self-host it from <https://github.com/firecrawl/firecrawl> (`docker compose up -d --build` in its folder, see its `SELF_HOST.md`).
  It should answer on `http://localhost:3002`. This repository does not embed it.
* **Ollama** (optional, for skill/graduation-year extraction): <https://ollama.com>, then `ollama pull qwen2.5:3b`.
  Containers reach it on the host, so it must listen on more than loopback:
  `OLLAMA_HOST=0.0.0.0 ollama serve` (Linux/WSL), or set it for the service/app on macOS and Windows.
  Extraction is **off by default** (`SERVE_EXTRACT=false`) because it is slow without a GPU.
* For development only: Python 3.12 and Node 20.

`host.docker.internal` is mapped for the scraper (`extra_hosts: host-gateway`), so Firecrawl and Ollama on your machine work on
Docker Desktop and on Linux. To use remote ones instead, set `FIRECRAWL_API_URL` / `OLLAMA_HOST` in `.env`.

## Quick start

```bash
cp .env.example .env
# Fill the REQUIRED values. Generate secrets with:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"     # SECRET_KEY, INGEST_TOKEN
#   POSTGRES_PASSWORD (letters/digits only), GRAFANA_ADMIN_PASSWORD
#   optionally ADMIN_EMAIL + ADMIN_PASSWORD to get an admin account (needed for the skill-gap and curriculum analytics)

docker compose up -d --build
docker compose ps          # wait until every service is "healthy" (first build takes a few minutes)
```

| Open | What |
|---|---|
| <http://localhost/> | The app (register, then browse; the first scrape runs at start-up and fills the list within minutes) |
| <http://localhost/api/docs> | Interactive API documentation |
| <http://localhost/grafana/> | Dashboards "API health" and "Scraper pipeline" (login with `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`) |
| <http://localhost:9090/targets> | Prometheus targets (all should be UP) |
| <http://localhost:8025/> | Mailpit inbox with the alert emails |

Run a scrape by hand (small, with the scraper's own settings and credentials):

```bash
docker compose exec scraper scraper run --source unstop --location India --limit 20 --push
docker compose exec scraper scraper run --source microsoft --query intern --location India --limit 5 --push --extract
docker compose exec scraper scraper sources      # list the sources
```

Stop: `docker compose down` (add `-v` to also delete the database and Grafana data).

### Deploying from prebuilt images

The release workflow publishes images to GitHub Container Registry. On a server with only Docker, the compose files and a `.env`:

```bash
# in .env:  IMAGE_PREFIX=ghcr.io/<owner>/job-aggregator-platform   IMAGE_TAG=latest   (or sha-<short>, or a version like 1.2.3)
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Behind HTTPS set `PUBLIC_URL=https://…` and `SESSION_COOKIE_SECURE=true`. Replace Mailpit with a real SMTP server through the
`SMTP_*` variables.

## Development

```bash
# Backend. A throwaway Postgres for the tests:
docker run -d --name jobs-test-pg -e POSTGRES_USER=jobs -e POSTGRES_PASSWORD=jobs -e POSTGRES_DB=jobs_test -p 5432:5432 postgres:16-alpine
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt -e "scraper[dev]"
cd backend && APP_ENV=dev pytest                      # 158 tests, including all 42 cases from testcases.md
ruff check . && mypy --ignore-missing-imports --explicit-package-bases --exclude 'alembic|tests' .
APP_ENV=dev DATABASE_URL=postgresql://jobs:jobs@localhost:5432/jobs alembic upgrade head
APP_ENV=dev DATABASE_URL=postgresql://jobs:jobs@localhost:5432/jobs uvicorn main:app --reload   # http://localhost:8000/docs

# Scraper
cd scraper && pytest && ruff check .

# Scraper <-> backend integration (fixture markdown -> mocked Ollama -> ingest -> queryable via the API)
pytest tests/integration

# Frontend (proxies /api to the backend on :8000, like nginx does)
cd frontend && npm ci && npm run dev                  # http://localhost:5173
npm run lint && npm run typecheck && npm test && npm run build
```

`APP_ENV=dev` relaxes the startup checks. Without it the backend **refuses to start** unless `SECRET_KEY` and `DATABASE_URL` are set.

### Whole-stack smoke test

```bash
bash scripts/smoke.sh        # builds and starts a separate stack, checks about 35 things, tears it down
KEEP=1 bash scripts/smoke.sh # leave it running on http://localhost:8080
```

It uses mock Firecrawl/Ollama servers (`scripts/ci_mocks.py`), so it needs no external services. It verifies every container is
healthy, nginx routing and headers, auth, a scraper pipeline run **twice** (no duplicates), an alert email arriving in Mailpit,
Prometheus targets UP and the provisioned Grafana dashboards. CI runs the same script.

## CI/CD

* `.github/workflows/ci.yml` (pull requests and branch pushes): backend lint, type-check, `alembic upgrade head` + `alembic check`
  against Postgres, tests; scraper lint and tests; scraper-to-backend integration tests; frontend lint, types, tests, build;
  builds all six images; then the compose smoke test. No real LLM is ever needed.
* `.github/workflows/release.yml` (push to `main` and `v*.*.*` tags): builds and pushes `ghcr.io/<owner>/<repo>-<service>` for
  `backend`, `scraper`, `frontend`, `nginx`, `prometheus`, `grafana`, tagged `sha-<short>`, `latest` (main) and the semver on tags,
  with OCI labels linking each package to the repository.

## Configuration reference

Everything is configured with environment variables; `.env.example` lists them with comments. `.env` is git-ignored.

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_DB` | `jobs` | Database user and name |
| `POSTGRES_PASSWORD` | **required** | Database password (letters and digits: it is placed in a URL) |
| `SECRET_KEY` | **required** | Signs session cookies |
| `INGEST_TOKEN` | **required** | Shared secret for scraper → backend ingest (`X-Ingest-Token`) |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | empty | If both set, this admin is created/updated at every backend start |
| `CORS_ORIGINS` | `http://localhost` | Allowed browser origins (comma separated) |
| `SESSION_COOKIE_SECURE` | `false` | `true` behind HTTPS |
| `PUBLIC_URL` | `http://localhost` | Used in emails and Grafana's root URL |
| `STALE_DAYS` | `14` | Days unseen before a scraped posting is marked inactive |
| `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` `SMTP_STARTTLS` `MAIL_FROM` | Mailpit | Alert email delivery |
| `ALERT_MIN_SCORE` | `60` | Minimum skills match (%) to be emailed |
| `FIRECRAWL_API_URL`, `FIRECRAWL_API_KEY` | `http://host.docker.internal:3002` | Firecrawl endpoint (key optional) |
| `OLLAMA_HOST`, `OLLAMA_MODEL` | `http://host.docker.internal:11434`, `qwen2.5:3b` | LLM extraction (`OLLAMA_URL` still read) |
| `SERVE_SOURCES` | `unstop,shine,internshala` | Sources scraped each cycle |
| `SERVE_LIMIT` | `300` | Max jobs per source per cycle |
| `SCRAPE_INTERVAL_HOURS` | `12` | Time between cycles |
| `RUN_ON_START` | `true` | Scrape right after start-up |
| `SERVE_EXTRACT` | `false` | Run Ollama extraction during scheduled scrapes |
| `REQUEST_DELAY_SECONDS`, `MAX_CONCURRENCY` | `1.5`, `2` | Politeness towards the sites |
| `GREENHOUSE_COMPANIES` | list | Greenhouse board tokens |
| `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` | `admin` / **required** | Grafana login |
| `PROMETHEUS_PORT`, `PROMETHEUS_RETENTION`, `MAILPIT_UI_PORT`, `HTTP_PORT` | `9090`, `15d`, `8025`, `80` | Ports / retention |
| `IMAGE_PREFIX`, `IMAGE_TAG` | local builds | Only for `docker-compose.prod.yml` |

Backend-only variables read by the app but not exposed in compose: `APP_ENV` (default `production`), `DATABASE_URL`,
`ROOT_PATH`, `ALERT_MAX_JOBS_PER_EMAIL`, `CURRICULUM_FILE`. Scraper-only: see `scraper/.env.example`.

## API overview

Interactive docs are at `/api/docs`. Session-cookie auth; routes marked *admin* need an admin account.

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/register`, `/auth/login`, `/auth/logout` | |
| GET / PATCH | `/me`, `/me/update` | profile, skills, `alerts_enabled` |
| GET | `/me/matches` | eligible jobs by skills match; `min_score`, `include_unmatched` |
| GET | `/jobs` | `q`, `job_type`, `location`, `skill`, `grad_year`, `source`, `scope` (`all`/`india`/`remote`/`india_remote`), `sort`, `hide_expired`, `limit`, `offset`; total in `X-Total-Count` |
| GET | `/jobs/{id}`, `/companies` | login required |
| POST | `/company` | login required |
| GET | `/analytics/skills`, `/analytics/companies` | login |
| GET | `/analytics/skill-gap`, `/analytics/curriculum` | *admin*; curriculum is `backend/curriculum.yaml` |
| POST | `/internal/jobs` | *admin session or `X-Ingest-Token`*: scraper ingest |
| POST | `/internal/alerts/run`, `/internal/maintenance/deactivate-stale` | admin session or ingest token; not exposed through nginx |
| GET | `/health` (checks the DB), `/metrics` | `/metrics` is internal (Prometheus); nginx returns 404 for it |

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `required variable … is missing a value` | Fill `POSTGRES_PASSWORD`, `SECRET_KEY`, `INGEST_TOKEN`, `GRAFANA_ADMIN_PASSWORD` in `.env`. |
| Backend exits: `SECRET_KEY must be set…` | Intended safety check. Set `SECRET_KEY` (outside Docker, use `APP_ENV=dev`). |
| `could not translate host name "db"` locally | You ran the backend outside Docker; use `localhost` in `DATABASE_URL`. |
| Shine finds nothing / `Connection refused … 3002` | Firecrawl isn't running or isn't reachable from the container. Check `curl localhost:3002`, and `FIRECRAWL_API_URL`. |
| `docker compose logs scraper` shows extraction failures | Ollama unreachable from the container. Start it with `OLLAMA_HOST=0.0.0.0`, check the model is pulled, or leave `SERVE_EXTRACT=false`. |
| `backend rejected the ingest token (HTTP 401)` | `INGEST_TOKEN` differs between services; both read the same `.env` value, so restart both after editing. |
| Login works but you are logged out on refresh | Serving over HTTPS without `SESSION_COOKIE_SECURE=true` or from another origin without it in `CORS_ORIGINS`. |
| 429 on sign-in | nginx limits sign-in/registration to 10 requests per minute per address. |
| Port 80 in use | Set `HTTP_PORT=8080` (and `PUBLIC_URL=http://localhost:8080`). |
| Grafana asks for a login | Use `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` from `.env`. |
| Lists are empty after start | The first scrape takes a few minutes; watch `docker compose logs -f scraper`. |
| Windows: `bad interpreter` in a container script | Line endings. `.gitattributes` forces LF for shell scripts and Dockerfiles; re-checkout after pulling it. |

## Repository layout

```
backend/     FastAPI app, Alembic migrations, curriculum.yaml, tests, Dockerfile
scraper/     source adapters, relevance filter, Ollama extraction, push + serve, tests, Dockerfile
frontend/    React + Vite + TypeScript app, tests, Dockerfile
infra/       nginx, prometheus (with rules), grafana (provisioning + dashboards)
tests/integration/   scraper -> backend end-to-end tests
scripts/     smoke.sh (whole-stack test), ci_mocks.py
docs/        AUDIT.md, PLAN.md, DECISIONS.md
firecrawl/   (git-ignored) optional local checkout of Firecrawl
```

## Known limitations

See the final section of [docs/AUDIT.md](docs/AUDIT.md) for the current list.
