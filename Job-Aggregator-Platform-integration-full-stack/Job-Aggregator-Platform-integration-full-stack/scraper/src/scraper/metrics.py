"""Prometheus metrics for the scraper pipeline (served by `scraper serve`)."""
from prometheus_client import Counter, Gauge, Histogram

PAGES = Counter("scraper_pages_total", "Pages fetched from sources", ["source", "outcome"])
JOBS = Counter("scraper_jobs_total", "Jobs processed by outcome (saved, unchanged, filtered, failed)", ["source", "outcome"])
PUSHED = Counter("scraper_push_records_total", "Records sent to the backend by result", ["status"])
PUSH_BATCHES = Counter("scraper_push_batches_total", "Batches sent to the backend by result (ok, failed)", ["result"])
RUNS = Counter("scraper_runs_total", "Scrape runs by result (ok, error)", ["source", "result"])
RUN_DURATION = Histogram("scraper_run_duration_seconds", "Duration of one source's scrape run", ["source"],
                         buckets=(5, 15, 30, 60, 120, 300, 600, 1200, 2400, 3600))
LAST_SUCCESS = Gauge("scraper_last_success_timestamp_seconds", "Unix time of the last successful run", ["source"])
RUN_ACTIVE = Gauge("scraper_run_in_progress", "1 while a scrape cycle is running")
