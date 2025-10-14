import contextlib
import functools
import shutil
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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
def preview(
    config_path: str = typer.Option("smilecms.yml", "--config", "-c", help="Path to configuration file."),
    host: str = typer.Option("127.0.0.1", "--host", help="Host interface to bind the preview server."),
    port: int = typer.Option(8000, "--port", "-p", help="Port for the preview server."),
    open_browser: bool = typer.Option(False, "--open-browser/--no-open-browser", help="Automatically open the site in a browser after starting."),
) -> None:
    """Serve the generated site directory with a simple HTTP server."""
    config = _load(config_path)
    if port < 0 or port > 65535:
        raise typer.BadParameter("Port must be between 0 and 65535.", param_name="port")

    output_dir = config.output_dir
    if not output_dir.exists():
        console.print(f"[bold red]Site output not found[/]: {output_dir}")
        console.print("Run 'smilecms build' to generate the static bundle before previewing.")
        raise typer.Exit(code=1)

    if not any(output_dir.iterdir()):
        console.print(
            f"[bold yellow]Warning[/]: {output_dir} is empty. Run 'smilecms build' to populate the site."
        )

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(output_dir))

    try:
        with _serve(host, port, handler) as server:
            bound_host, bound_port = server.server_address[:2]
            url_host = "127.0.0.1" if bound_host in {"0.0.0.0", ""} else bound_host
            site_url = f"http://{url_host}:{bound_port}/"
            console.print(
                f"[bold green]Preview server[/]: serving {output_dir} at {site_url} "
                "(press Ctrl+C to stop)"
            )
            if open_browser:
                webbrowser.open(site_url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                console.print("\n[bold yellow]Stopping preview server...[/]")
    except OSError as exc:
        console.print(f"[bold red]Failed to start preview server[/]: {exc}")
        raise typer.Exit(code=1) from exc

@app.command()
def clean(
    config_path: str = typer.Option("smilecms.yml", "--config", "-c", help="Path to configuration file."),
    include_cache: bool = typer.Option(False, "--cache", help="Also remove the configured cache directory."),
) -> None:
    """Remove generated artifacts (site bundle, media derivatives, and optional cache)."""
    config = _load(config_path)
    targets: list[tuple[str, Path]] = [
        ("site output", config.output_dir),
        ("media derivatives", config.media_processing.output_dir),
    ]
    if include_cache:
        targets.append(("cache", config.cache_dir))

    removed = 0
    for label, path in targets:
        if path.exists():
            console.print(f"[bold green]Removing[/]: {label} ({path})")
            _remove_path(path)
            removed += 1
        else:
            console.print(f"[bold yellow]Skipping[/]: {label} ({path}) not found")

    console.print(
        f"[bold green]Clean complete[/]: removed {removed} director{'y' if removed == 1 else 'ies'}."
    )


def _load(path: str) -> Config:
    try:
        return load_config(path)
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"Config file not found: {path}") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


class _ThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


@contextlib.contextmanager
def _serve(
    host: str,
    port: int,
    handler: type[SimpleHTTPRequestHandler] | functools.partial,
) -> ThreadingHTTPServer:
    server = _ThreadingHTTPServer((host, port), handler)
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink(missing_ok=True)
