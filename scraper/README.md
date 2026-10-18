# Scraper module

Discovers and stores job postings. Currently supports:
- **Microsoft**: public JSON API, clean structured fields
- **Internshala**: server-rendered HTML listing pages (50 per page), parsed with BeautifulSoup
- **Google**: job data embedded in the search-results page itself (`AF_initDataCallback`), no detail fetch needed
- **Y Combinator**: startup jobs; listing and job pages embed their data as JSON (`data-page`), full descriptions included
- **Unstop**: India's student jobs/internships platform; public JSON API with full descriptions, plus who-may-apply ("Fresher", "Experienced Professionals") and work-function tags
- **Shine**: India's fresher/entry-level job portal. A Next.js app with no public API; this is the source that goes through **Firecrawl**, which renders the search and job pages to clean markdown
- **Greenhouse**: one adapter for many companies. Greenhouse hosts public hiring-board APIs; the companies come from `GREENHOUSE_COMPANIES` (or `--company`). One request per company returns every posting with its description.

Every source goes through one shared filter (`relevance.py`): **software roles only** (no design, marketing, sales, product/program management, hardware) that an **undergrad can apply for** (internships, new grad / early career / entry level, or at most 1 year of experience required; senior/staff/lead, PhD-only and 2+ year roles are dropped). A posting with no entry-level signal is dropped too. Dropped jobs are counted as `filtered` in the run summary and logged, never stored.

Not built, by design: **Indeed** (Cloudflare CAPTCHA page on search URLs), **Naukri** (its search API requires solving a reCAPTCHA) and **Glassdoor**
(real job-search URLs are blocked by an active bot-detection wall). Both are beyond a plain
robots.txt-respecting scraper; see "Notes on specific sources" below.

LLM extraction (Ollama) is an optional stage: add `--extract` to a run. See "LLM extraction" below.

## Run locally
```bash
python3.12 -m venv venv && ./venv/bin/pip install -e ".[dev]"
cp .env.example .env

# Computer Science internships (default for Internshala)
./venv/bin/scraper run --source internshala --limit 20

# Other Internshala categories: software-engineering, data-science, ai-ml (anything else falls back to computer-science)
./venv/bin/scraper run --source internshala --query software-engineering --limit 20

# Microsoft roles (specify query)
./venv/bin/scraper run --source microsoft --query intern --location India --limit 20

# Google roles (specify query; only 20 results per query+location, see notes below)
./venv/bin/scraper run --source google --query "software engineering intern" --location India --limit 20

# Y Combinator startups (queries don't apply; location is a page slug like india, new-york, remote)
./venv/bin/scraper run --source ycombinator --location India --limit 20

# Unstop: Indian student jobs + internships (default queries are software terms; --query overrides)
./venv/bin/scraper run --source unstop --location India --limit 300

# Greenhouse: many companies, one adapter (default list in .env.example; --company overrides it)
./venv/bin/scraper run --source greenhouse --location India --limit 50
./venv/bin/scraper run --source greenhouse --company stripe --company rubrik --location India

# Shine (goes through Firecrawl, which must be running, see below): fresher software jobs; --location takes India or a city
./venv/bin/scraper run --source shine --location India --limit 40
./venv/bin/scraper run --source shine --query "java developer fresher" --location Bengaluru

# List sources and run tests
./venv/bin/scraper sources
./venv/bin/pytest                   # unit tests
```
Output: `data/jobs.jsonl` (one job per line; re-runs skip unchanged jobs) and
`data/dead_letter.jsonl` (jobs that failed, with the error).

## Run with Docker
```bash
# Computer Science internships
docker compose run --rm scraper run --source internshala --limit 20

# Other sources/categories
docker compose run --rm scraper run --source internshala --query data-science --limit 20
docker compose run --rm scraper run --source microsoft --query intern --location India --limit 20
```

## Add a new website
1. Create `src/scraper/adapters/<site>.py` with a `SourceAdapter` subclass.
   - Site has a JSON API: implement `discover`, `fetch`, `normalize` yourself (see `microsoft.py`).
   - Server-rendered HTML: parse with BeautifulSoup, same pattern as Internshala.
   - No API or HTML: subclass `FirecrawlAdapter`; implement only `discover` and `extract_external_id` (uses Firecrawl for SPA sites).
2. Add one line to `REGISTRY` in `adapters/__init__.py`.
3. Add unit tests in `tests/test_<site>.py` (fixtures in `fixtures/`).

Current architecture requires only one class per site; adding Internshala and Microsoft each took ~150 lines and 5 minutes.

## How the pipeline flows
discover -> fetch -> normalize -> (skip if content hash unchanged) -> store.
`source`, `company`, `url`, `external_id`, `scraped_at`, `content_hash` are set by code, never by the source or an LLM.

## LLM extraction (optional)
`scraper run ... --extract` sends each kept posting that has enough text (`EXTRACTION_MIN_CHARS`, default 300) to a
local Ollama model and stores the answer under `extraction` in the record, separate from everything the code sets.
It fills: `skills`, `degree_required`, `graduation_years`, `work_mode`, `salary_min/max/currency/period`,
`work_authorization_restricted` + the quoted sentence.

```bash
ollama serve &                 # needs Ollama installed; default model: qwen2.5:3b (fits a 4 GB GPU)
ollama pull qwen2.5:3b
./venv/bin/scraper run --source greenhouse --location India --extract
./venv/bin/scraper extract-file posting.txt --title "Software Engineer"   # try the model on one saved posting
```
- **Nothing is trusted blindly.** Every value is checked against the posting text (`extraction.ground`): skills and
  years must appear in it, a work-authorization restriction needs a quotable sentence, a degree level needs a
  matching word, salary figures must appear and units (lakh, K...) are multiplied in code, not by the model.
  Whatever fails is set to null.
- **Re-runs are cheap.** A job is re-extracted only if its text changed or the model/prompt (`model|prompt_version`) did.
- **Failures never lose a job.** It is saved without `extraction`, logged in `dead_letter.jsonl` (stage `extraction`), and retried next run.
- `jobs.jsonl` is append-only: if a job is updated, a new line is added and the **last line for an id wins**.
- Limits of a 3B model: skills can include loose phrases on non-technical text, and when a posting lists degree
  alternatives ("Master's or Doctorate") it may not pick the lowest. Listing-card sources (Internshala) have too
  little text and are skipped.

## Firecrawl (used by Shine)
Firecrawl is self-hosted from the `firecrawl/` folder: `cd ../firecrawl && docker compose up -d --build`, then it answers on
`localhost:3002` (the default `FIRECRAWL_API_URL`). `FirecrawlAdapter.scrape(url)` renders any page to cleaned markdown and checks
the site's robots.txt first. The self-hosted build has no Fire Engine, so it cannot click, type or paginate with buttons: only
what a page shows after loading is available. Sites that need those (e.g. Infosys careers shows only 10 of 1,700 jobs and ignores
URL filters) are not usable with it.

## Notes on specific sources

**Shine**: `shine.com/job-search/<query>-jobs[-in-<city>][-<page>]` lists 20 postings per page (the `?page=` parameter is
ignored). Cards give title, company, experience range ("0 to 4 Yrs") and skills; each posting's page adds the full description,
location and job type. Listings are cut by the shared filter like every source; cards asking for 2+ years without a fresher/intern
title are dropped before the detail page is fetched. Discovery reads at most 5 pages per query and location. Terms of service were not reviewed.

**Microsoft**: Uses the public JSON API (`/api/pcsx/search` and `/position_details`). The rendered page is ~490K chars of embedded config; the API returns clean structured fields. robots.txt explicitly allows `/api/pcsx`.

**Internshala**: Server-rendered HTML listing pages at `/internships/<category>/` and `/page-N/`. Each page has 50 cards with title, company, location, stipend, duration, and skills. Defaults to `computer-science` category for CS students; also supports `software-engineering` (Internshala's `software-development` category), `data-science`, `ai-ml` (`artificial-intelligence-ai`), `machine-learning`, `cyber-security`. If a category page redirects (Internshala renamed a slug), the adapter logs a warning and skips it instead of reading the all-categories list. Detail pages blocked by robots.txt, so we extract from cards only (no full description). Robots.txt allows the listing pages.

**Google**: The careers search-results page embeds full job data (title, HTML responsibilities/qualifications, company, locations, timestamps) in a `AF_initDataCallback({key: 'ds:1', ...})` JS blob — no separate detail-page fetch needed. robots.txt blocks any URL with a `page=` param for generic crawlers, so we can't paginate past the first 20 results per query+location; `discover()` covers more ground by trying each configured query term, same dedup approach as Microsoft. Qualifications HTML has Minimum/Preferred sections marked by `<h3>` headers, split accordingly.

**Y Combinator**: Role page `/jobs/role/software-engineer[/<location>]` lists postings with type, role, min experience and skills; each job's page adds the description. The data is unreliable on its own (the software page contains marketing roles; "new grads ok" appears on Staff roles), which is why the shared filter checks titles too. Needs `Accept: text/html` (YC 404s on the client's default JSON Accept). Location pages are loose (the India page lists remote-US jobs).

**Unstop**: `unstop.com/api/public/opportunity/search-result?opportunity=jobs|internships&searchTerm=...` is what the site's own JS app calls. robots.txt has `Allow: /api/public/*` and `Disallow: /api/*`; the longer rule wins, so the API is allowed (the scraper's robots parser does longest-match). Each result carries the full HTML description. Experience numbers are almost always empty, so the entry-level signal is the posting's eligibility list: kept if it includes Fresher, Undergraduate, Engineering Students or All; "Experienced Professionals"-only and postgraduate-only postings are dropped. Postings must also carry a software work function (e.g. "Software Development", "Data Engineering"); this removed Network Administration, IT Operations, annotation work and similar. Work-from-home postings have no location and are kept. Terms of service were not reviewed.

**Greenhouse**: `boards-api.greenhouse.io/v1/boards/<token>/jobs?content=true` is public and documented. Add a company by adding its board token (the name in its Greenhouse URL) to `GREENHOUSE_COMPANIES`. Locations are free text ("Bengaluru, India; Mumbai, India", "Bangalore", "Remote - India"), matched by `location.py`. The API has no visa field, and most India postings at these companies are senior (2-7+ years), so few survive the undergrad filter; entry-level roles show up mostly as seasonal intern postings. Titles saying "US Citizen" or "clearance" are dropped.

**Indeed** (not built): robots.txt allows `/`, but search URLs return a Cloudflare "Security Check" CAPTCHA page. Active anti-bot control; not attempted.

**Naukri** (not built): robots.txt itself allows job listing pages, but they're rendered client-side — the actual data comes from `jobapi/v3/search`, which returns `406 recaptcha required`. That's an active anti-bot control, not a robots.txt restriction, so there's no clean way to fetch this without solving a CAPTCHA.

**Glassdoor** (not built): Real job-search URLs (e.g. `/Job/...-SRCH_...htm`) return a "Security | Glassdoor" interstitial (bot-detection block page) even with a plain browser user agent. Same category as Naukri — an active defense, not something we'll try to get around.
