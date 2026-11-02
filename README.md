# Job-Aggregator-Platform

## Backend API

Internal ingestion and maintenance endpoints accept `X-Ingest-Token` or an authenticated admin
session. The legacy `ingest-token` header and `/internal/trigger_alerts` route remain supported.
Job ingestion reports per-record outcomes and does not retire jobs omitted from a partial batch.
Use `POST /internal/maintenance/deactivate-stale?days=14` to retire scraper-sourced jobs not seen
within the selected number of days.

`GET /jobs` supports `q`, `company_id`, `company_group`, `job_type`, `location`, `company`, `skill`, `grad_year`,
`source`, `scope`, `active_only`, `hide_expired`, and `sort` filters. It returns `X-Total-Count`;
page sizes above 100 are capped. Job responses include source and freshness metadata.

Analytics routes are available at `/analytics/skills`, `/analytics/companies`,
`/analytics/skill-gap`, and `/analytics/curriculum`. Skill-gap and curriculum analytics require an
admin session. Edit `curriculum.yaml` to change the courses and skills used by curriculum analytics.
`/health` checks database connectivity, and `/metrics` is available to the monitoring service.

Students can track applications with `POST /me/applications` (`job_id`, optional `status` and
`notes`), list them with `GET /me/applications` (optional `status` filter), update a record with
`PATCH /me/applications/{application_id}`, or remove it with `DELETE /me/applications/{application_id}`.
Statuses are `saved`, `applied`, `assessment`, `interview`, `offer`, `rejected`, and `withdrawn`.
Each student can track a given job once; application records are private to their owner.
The frontend exposes these features through job filters, a personalized dashboard, and an application
tracker. Profiles accept text-based PDF resumes; upload parses skills, CGPA, and graduation year.
Admins can review platform analytics and manage the company directory from the admin page.

## Run the full stack

The React frontend, scraper, reverse proxy, monitoring dashboards, and CI/CD workflows are included
alongside the backend modules in `backend/`. Docker Compose builds the API image from that directory.

1. Copy `.env.example` to `.env`.
2. Set `POSTGRES_PASSWORD`, `SECRET_KEY`, and `INGEST_TOKEN` to private values.
3. Start the stack with `docker compose up -d --build`.

Open `http://localhost` for the frontend, `http://localhost/api/docs` for the API, and
`http://localhost/grafana/` for monitoring. The integration frontend uses this backend's existing
embedding-based match scores. Run `docker compose down` to stop the stack.

The scheduled scraper includes Unstop, Shine, Internshala, Google Careers, Microsoft Careers, and
Amazon Jobs by default. Amazon listings are retrieved from Amazon's public `amazon.jobs` search JSON
endpoint; source selection and per-source run limits can be changed with `SERVE_SOURCES` and
`SERVE_LIMIT` in `.env`.