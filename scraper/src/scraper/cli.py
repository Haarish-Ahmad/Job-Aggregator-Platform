import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from scraper.adapters import REGISTRY, get_adapter
from scraper.config import Settings
from scraper.extraction import OllamaExtractor
from scraper.http import PoliteClient
from scraper.models import SearchFilters
from scraper.pipeline import run as run_pipeline
from scraper.storage.jsonl import JsonlStorage

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
    default_queries = query or REGISTRY[source].default_queries or settings.query_list
    filters = SearchFilters(
        queries=default_queries,
        locations=location or settings.location_list,
        limit=limit,
    )
    client = PoliteClient(settings.user_agent, settings.request_delay_seconds)
    extractor = OllamaExtractor(settings) if extract else None
    try:
        adapter = get_adapter(source, client=client, settings=settings)
        storage = JsonlStorage(settings.output_dir)
        stats = run_pipeline(adapter, filters, storage, settings, extractor)
    finally:
        client.close()
        if extractor:
            extractor.close()
    typer.echo(
        f"discovered={stats.discovered} saved={stats.saved} "
        f"unchanged={stats.unchanged} filtered={stats.filtered} failed={stats.failed}"
        + (f" extracted={stats.extracted} extraction_failed={stats.extraction_failed}" if extract else "")
    )
    typer.echo(f"output: {storage.jobs_path}")
    if stats.failed:
        typer.echo(f"failures: {storage.dead_letter_path}")


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
