import time

import typer
from rich.console import Console

from .config import Config, load_config
from .ingest import load_documents
from .manifests import ManifestGenerator, write_manifest_pages
from .media import apply_variants_to_documents, collect_media_plan, process_media_plan
from .reporting import (
    assemble_report,
    build_document_stats,
    build_manifest_stats,
    build_media_stats,
    write_report,
)
from .validation import DocumentValidationError

console = Console()
app = typer.Typer(help="SmileCMS static publishing toolkit.")

@app.command()
def build(config_path: str = "smilecms.yml") -> None:
    """Run a full rebuild of site artifacts."""
    config = _load(config_path)
    try:
        documents = load_documents(config)
    except DocumentValidationError as error:
        console.print(f"[bold red]Validation failed[/]: {error}")
        raise typer.Exit(code=1)

    start = time.perf_counter()

    document_stats = build_document_stats(documents)

    media_plan = collect_media_plan(documents, config)
    media_result = process_media_plan(media_plan, config)
    apply_variants_to_documents(documents, media_result.variants)

    generator = ManifestGenerator()
    pages = generator.build_pages(documents, prefix="content")
    manifest_dir = config.output_dir / "manifests"
    written = write_manifest_pages(pages, manifest_dir)
    manifest_stats = build_manifest_stats(pages)
    media_stats = build_media_stats(media_plan, media_result)

    duration = time.perf_counter() - start
    report = assemble_report(
        project=config.project_name,
        duration_seconds=duration,
        documents=document_stats,
        manifests=manifest_stats,
        media=media_stats,
    )
    report_path = write_report(report, config.output_dir)

    console.print(
        f"[bold green]Documents[/]: {document_stats.total} "
        f"(published {document_stats.published}, drafts {document_stats.drafts}, archived {document_stats.archived})"
    )
    console.print(
        f"[bold green]Manifests[/]: {manifest_stats.pages} page(s) with {manifest_stats.items} item(s); "
        f"written {len(written)} file(s) to {manifest_dir}"
    )
    console.print(
        f"[bold green]Media[/]: {media_stats.assets_processed}/{media_stats.assets_planned} asset(s) "
        f"produced {media_stats.variants_generated} variant(s), "
        f"copied {media_stats.assets_copied} asset(s); "
        f"{media_stats.tasks_processed}/{media_stats.tasks_planned} image task(s) completed "
        f"({media_stats.tasks_skipped} skipped)"
    )
    console.print(
        f"[bold green]Report[/]: {report_path} "
        f"(duration {duration:.2f}s)"
    )
    if report.warnings:
        console.print("[bold yellow]Warnings:[/]")
        for warning in report.warnings:
            console.print(f"- {warning}")

@app.command()
def preview(config_path: str = "smilecms.yml") -> None:
    """Launch local preview server (stub)."""
    config = _load(config_path)
    console.print(f"[bold yellow]TODO[/]: start preview for {config.project_name}")

@app.command()
def clean(config_path: str = "smilecms.yml") -> None:
    """Remove generated artifacts (stub)."""
    config = _load(config_path)
    console.print(f"[bold red]TODO[/]: clean artifacts for {config.project_name}")

def _load(path: str) -> Config:
    try:
        return load_config(path)
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"Config file not found: {path}") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
