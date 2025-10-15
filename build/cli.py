import contextlib
import functools
import shutil
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console

from .articles import write_article_pages
from .config import Config, load_config
from .gallery import apply_derivatives as apply_gallery_derivatives
from .gallery import export_datasets as export_gallery_datasets
from .gallery import prepare_workspace as prepare_gallery_workspace
from .ingest import load_documents
from .manifests import ManifestGenerator, write_manifest_pages
from .media import (
    MediaAuditResult,
    audit_media,
    apply_variants_to_documents,
    collect_media_plan,
    process_media_plan,
)

if TYPE_CHECKING:
    from .media.audit import ReferenceUsage
from .music import export_music_catalog
from .reporting import (
    assemble_report,
    build_document_stats,
    build_manifest_stats,
    build_media_stats,
    write_report,
)
from .staging import StagingResult, reset_directory, stage_static_site
from .state import BuildTracker
from .validation import DocumentValidationError

console = Console()
app = typer.Typer(help="SmileCMS static publishing toolkit.")
audit_app = typer.Typer(help="Audit workspace content and media.")
app.add_typer(audit_app, name="audit")

@app.command()
def build(
    config_path: str = typer.Option("smilecms.yml", "--config", "-c", help="Path to configuration file."),
    force: bool = typer.Option(False, "--force", help="Ignore incremental cache and perform a full rebuild."),
) -> None:
    """Run a full rebuild of site artifacts."""
    config = _load(config_path)
    tracker = BuildTracker(config, Path(config_path))
    fingerprints = tracker.compute_fingerprints()
    change_summary = tracker.summarize_changes(fingerprints)

    if force:
        console.print("[bold yellow]Force rebuild[/]: clearing output directories before regenerating.")
        reset_directory(config.output_dir)
        reset_directory(config.media_processing.output_dir)
    else:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.media_processing.output_dir.mkdir(parents=True, exist_ok=True)
        if change_summary.first_run:
            console.print(
                "[bold yellow]Incremental build[/]: initializing cache; no previous state detected."
            )
        elif change_summary.changed_keys:
            categories = ", ".join(sorted(change_summary.changed_keys))
            console.print(
                f"[bold green]Incremental build[/]: changes detected in {categories}."
            )
        else:
            console.print(
                "[bold blue]Incremental build[/]: no input changes detected; reusing cached artifacts."
            )

    gallery_workspace = prepare_gallery_workspace(config)
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

    media_line = (
        f"[bold green]Media[/]: {media_stats.assets_processed}/{media_stats.assets_planned} asset(s) "
        f"produced {media_stats.variants_generated} variant(s); "
        f"{media_stats.assets_copied} copied"
    )
    if media_stats.assets_reused:
        media_line += f", {media_stats.assets_reused} reused"
    media_line += ". "
    media_line += (
        f"{media_stats.tasks_processed}/{media_stats.tasks_planned} image task(s) rendered"
    )
    if media_stats.tasks_reused:
        media_line += f", {media_stats.tasks_reused} reused"
    media_line += f" ({media_stats.tasks_skipped} skipped)"
    if media_stats.artifacts_pruned:
        media_line += f"; removed {media_stats.artifacts_pruned} stale file(s)"
    console.print(media_line)

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

    previous_templates = tracker.previous_template_paths or None
    stage_result: StagingResult = stage_static_site(
        config,
        previous_template_paths=previous_templates,
    )
    if stage_result.total:
        console.print(
            f"[bold green]Static bundle[/]: staged {stage_result.total} item(s) into {config.output_dir}"
        )
    else:
        console.print(
            f"[bold yellow]Static bundle[/]: no template assets found at {config.templates_dir}"
        )
    if stage_result.removed_templates:
        console.print(
            f"[bold yellow]Static bundle[/]: removed {len(stage_result.removed_templates)} stale template asset(s)"
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

    tracker.persist(fingerprints, stage_result.template_paths)

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


@audit_app.command("media")
def audit_media_command(
    config_path: str = typer.Option(
        "smilecms.yml", "--config", "-c", help="Path to configuration file."
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of human formatted output.",
    ),
) -> None:
    """Inspect media references and files for missing or misplaced assets."""
    config = _load(config_path)
    documents = load_documents(config)
    result = audit_media(documents, config)
    if json_output:
        console.print_json(data=_media_audit_payload(result))
        return
    _print_media_audit(result)


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


def _print_media_audit(result: MediaAuditResult) -> None:
    summary_line = (
        f"[bold green]Media audit[/]: discovered {result.total_assets} source asset(s); "
        f"{result.valid_references}/{result.total_references} referenced path(s) resolved."
    )
    console.print(summary_line)

    issues = 0

    if result.out_of_bounds_references:
        issues += 1
        console.print("[bold red]Out-of-bounds references[/]:")
        for path in sorted(result.out_of_bounds_references):
            usage = result.out_of_bounds_references[path]
            console.print(_format_reference_line(path, usage))

    if result.missing_references:
        issues += 1
        console.print("[bold red]Missing referenced assets[/]:")
        for path in sorted(result.missing_references):
            usage = result.missing_references[path]
            expected = usage.expected_path.as_posix() if usage.expected_path else "unknown location"
            console.print(_format_reference_line(path, usage, suffix=f"expected: {expected}"))

    if result.orphan_files:
        issues += 1
        console.print("[bold yellow]Orphaned assets[/]:")
        for path in sorted(result.orphan_files):
            location = _display_path(result.orphan_files[path])
            console.print(f"- {path} (source: {location})")

    if result.stray_files:
        issues += 1
        console.print("[bold yellow]Assets stored outside allowed roots[/]:")
        for key in sorted(result.stray_files):
            console.print(f"- {_display_path(result.stray_files[key])}")

    if issues == 0:
        console.print("[bold green]No media issues detected.[/]")


def _media_audit_payload(result: MediaAuditResult) -> dict:
    def serialize_usage(path: str, usage: "ReferenceUsage") -> dict:
        payload: dict[str, object] = {
            "path": path,
            "documents": sorted(usage.documents),
        }
        if usage.roles:
            payload["roles"] = sorted(usage.roles)
        if usage.expected_path:
            payload["expected_path"] = usage.expected_path.as_posix()
        return payload

    payload = {
        "summary": {
            "total_assets": result.total_assets,
            "total_references": result.total_references,
            "valid_references": result.valid_references,
            "missing_references": len(result.missing_references),
            "out_of_bounds_references": len(result.out_of_bounds_references),
            "orphan_assets": len(result.orphan_files),
            "stray_assets": len(result.stray_files),
        },
        "missing_references": [
            serialize_usage(path, result.missing_references[path]) for path in sorted(result.missing_references)
        ],
        "out_of_bounds_references": [
            serialize_usage(path, result.out_of_bounds_references[path])
            for path in sorted(result.out_of_bounds_references)
        ],
        "orphan_assets": [
            {
                "path": path,
                "source_path": _display_path(result.orphan_files[path]),
            }
            for path in sorted(result.orphan_files)
        ],
        "stray_assets": [
            {
                "path": _display_path(result.stray_files[key]),
            }
            for key in sorted(result.stray_files)
        ],
    }
    return payload


def _format_reference_line(path: str, usage: "ReferenceUsage", suffix: str | None = None) -> str:
    details: list[str] = []
    if usage.documents:
        details.append(f"documents: {', '.join(sorted(usage.documents))}")
    if usage.roles:
        details.append(f"roles: {', '.join(sorted(usage.roles))}")
    if suffix:
        details.append(suffix)
    detail_text = f" ({'; '.join(details)})" if details else ""
    return f"- {path}{detail_text}"


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


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
