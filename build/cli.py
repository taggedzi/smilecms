import time

import typer
from rich.console import Console

from .articles import write_article_pages
from .config import Config, load_config
from .gallery import apply_derivatives as apply_gallery_derivatives
from .gallery import export_datasets as export_gallery_datasets
from .gallery import prepare_workspace as prepare_gallery_workspace
from .ingest import load_documents
from .manifests import ManifestGenerator, write_manifest_pages
from .media import apply_variants_to_documents, collect_media_plan, process_media_plan
from .music import export_music_catalog
from .reporting import (
    assemble_report,
    build_document_stats,
    build_manifest_stats,
    build_media_stats,
    write_report,
)
from .staging import reset_directory, stage_static_site
from .validation import DocumentValidationError

console = Console()
app = typer.Typer(help="SmileCMS static publishing toolkit.")

@app.command()
def build(config_path: str = "smilecms.yml") -> None:
    """Run a full rebuild of site artifacts."""
    config = _load(config_path)
    gallery_workspace = prepare_gallery_workspace(config)
    reset_directory(config.output_dir)
    reset_directory(config.media_processing.output_dir)
    try:
        documents = load_documents(config, gallery_workspace=gallery_workspace)
    except DocumentValidationError as error:
        console.print(f"[bold red]Validation failed[/]: {error}")
        raise typer.Exit(code=1)

    start = time.perf_counter()

    document_stats = build_document_stats(documents)

    media_plan = collect_media_plan(documents, config)
    media_result = process_media_plan(media_plan, config)
    apply_variants_to_documents(documents, media_result.variants)
    updated_gallery = apply_gallery_derivatives(gallery_workspace, media_result, config)

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
        f"[bold green]Gallery[/]: {gallery_workspace.collection_count()} collection(s) "
        f"with {gallery_workspace.image_count()} image(s); "
        f"{len(gallery_workspace.collection_writes)} collection sidecar(s) "
        f"and {len(gallery_workspace.image_writes)} image sidecar(s) updated; "
        f"{updated_gallery} derivative mapping(s) refreshed"
    )
    console.print(
        f"[bold green]Report[/]: {report_path} "
        f"(duration {duration:.2f}s)"
    )
    staged = stage_static_site(config)
    if staged:
        console.print(
            f"[bold green]Static bundle[/]: staged {len(staged)} item(s) into {config.output_dir}"
        )
    else:
        console.print(
            f"[bold yellow]Static bundle[/]: no template assets found at {config.templates_dir}"
        )
    article_pages = write_article_pages(documents, config)
    if article_pages:
        console.print(
            f"[bold green]Articles[/]: rendered {len(article_pages)} page(s) in {config.output_dir / 'posts'}"
        )
    export_gallery_datasets(gallery_workspace, config)
    if gallery_workspace.data_writes:
        console.print(
            f"[bold green]Gallery data[/]: wrote {len(gallery_workspace.data_writes)} file(s) to "
            f"{config.output_dir / config.gallery.data_subdir}"
        )
    music_result = export_music_catalog(documents, config)
    if music_result.written:
        console.print(
            f"[bold green]Music catalog[/]: exported {music_result.tracks} track(s); "
            f"wrote {len(music_result.written)} file(s) to {config.output_dir / config.music.data_subdir}"
        )
    warnings = list(report.warnings)
    warnings.extend(gallery_workspace.warnings)
    warnings.extend(music_result.warnings)
    if warnings:
        console.print("[bold yellow]Warnings:[/]")
        for warning in warnings:
            console.print(f"- {warning}")
    if gallery_workspace.errors:
        console.print("[bold red]Gallery errors:[/]")
        for error in gallery_workspace.errors:
            console.print(f"- {error}")

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
