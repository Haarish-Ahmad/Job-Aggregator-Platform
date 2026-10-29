import json
import logging
import signal
import threading
from pathlib import Path
from typing import Annotated

import typer

from scraper.adapters import REGISTRY
from scraper.config import Settings
from scraper.extraction import OllamaExtractor
from scraper.http import PoliteClient
from scraper.runner import build_filters, run_source
from scraper.serve import serve as serve_forever

app = typer.Typer(help="Career-site scraper", no_args_is_help=True)


@app.command()
def sources() -> None:
    """List available sources."""
    for name in sorted(REGISTRY):
        typer.echo(name)


@app.command()
def run(
    source: Annotated[str, typer.Option(help="Source name, see `scraper sources`")],
    query: Annotated[list[str] | None, typer.Option(help="Search query (repeatable). For internshala: computer-science (default), software-engineering, data-science, ai-ml")] = None,
    location: Annotated[list[str] | None, typer.Option(help="Location (repeatable)")] = None,
    company: Annotated[list[str] | None, typer.Option(help="Greenhouse board token (repeatable); default: GREENHOUSE_COMPANIES")] = None,
    limit: Annotated[int, typer.Option(help="Max jobs to fetch this run")] = 20,
    extract: Annotated[bool, typer.Option(help="Run LLM extraction (needs Ollama running)")] = False,
    push: Annotated[bool, typer.Option(help="Also send every job to the backend (BACKEND_URL + INGEST_TOKEN)")] = False,
    verbose: bool = False,
) -> None:
    """Discover, fetch and store job postings (software roles an undergrad can apply for)."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings()
    if company:
        settings.greenhouse_companies = ",".join(company)
    if source not in REGISTRY:
        raise typer.BadParameter(f"Unknown source {source!r}. Available: {', '.join(sorted(REGISTRY))}")
    if push and not settings.ingest_token:
        raise typer.BadParameter("--push needs INGEST_TOKEN to be set (the same value the backend uses)")
    filters = build_filters(source, settings, query, location, limit)
    client = PoliteClient(settings.user_agent, settings.request_delay_seconds)
    try:
        stats, push_stats, storage = run_source(source, settings, client, filters, extract=extract, push=push)
    finally:
        client.close()
    typer.echo(
        f"discovered={stats.discovered} saved={stats.saved} "
        f"unchanged={stats.unchanged} filtered={stats.filtered} failed={stats.failed}"
        + (f" extracted={stats.extracted} extraction_failed={stats.extraction_failed}" if extract else "")
    )
    if push_stats:
        typer.echo(f"backend: {push_stats.summary()}")
    typer.echo(f"output: {storage.jobs_path}")
    if stats.failed or (push_stats and (push_stats.failed or push_stats.rejected)):
        typer.echo(f"failures: {storage.dead_letter_path}")


@app.command()
def serve(
    verbose: bool = False,
) -> None:
    """Run forever: scrape SERVE_SOURCES every SCRAPE_INTERVAL_HOURS, push to the backend, serve /metrics and /health."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings()
    if not settings.ingest_token:
        raise typer.BadParameter("serve needs INGEST_TOKEN to be set (the same value the backend uses)")
    bad = [s for s in settings.serve_source_list if s not in REGISTRY]
    if bad:
        raise typer.BadParameter(f"Unknown SERVE_SOURCES: {', '.join(bad)}. Available: {', '.join(sorted(REGISTRY))}")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    serve_forever(settings, stop)


@app.command("extract-file")
def extract_file(
    path: Annotated[Path, typer.Argument(help="Text file containing a job posting")],
    title: Annotated[str, typer.Option(help="Job title, if known")] = "",
) -> None:
    """Run LLM extraction on one saved posting and print the result (for tuning prompts/models)."""
    settings = Settings()
    extractor = OllamaExtractor(settings)
    try:
        result = extractor.extract(title, path.read_text())
    finally:
        extractor.close()
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    app()
