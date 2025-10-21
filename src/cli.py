"""CLI entrypoints for SmileCMS build tooling."""

import contextlib
from dataclasses import dataclass
import shutil
import time
import webbrowser
from enum import Enum
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Iterable, Iterator, Sequence, cast

import typer
from rich.console import Console

from .articles import write_article_pages
from .config import Config, MediaProcessingConfig, load_config
from .feeds import generate_feeds
from .gallery import apply_derivatives as apply_gallery_derivatives
from .gallery import export_datasets as export_gallery_datasets
from .gallery import prepare_workspace as prepare_gallery_workspace
from .htmlvalidate import (
    HtmlValidationReport,
    HtmlValidatorError,
    HtmlValidatorUnavailableError,
    validate_html,
)
from .jsvalidate import (
    JsValidationReport,
    JsValidatorError,
    JsValidatorUnavailableError,
    validate_javascript,
)
from .ingest import load_documents
from .manifests import ManifestGenerator, write_manifest_pages
from .media import (
    MediaAuditResult,
    apply_variants_to_documents,
    audit_media,
    collect_media_plan,
    process_media_plan,
)
from .music import MusicExportResult, export_music_catalog
from .pages import write_gallery_page, write_music_page
from .reporting import (
    BuildReport,
    assemble_report,
    build_document_stats,
    build_manifest_stats,
    build_media_stats,
    write_report,
)
from .scaffold import ScaffoldError, ScaffoldResult, normalize_slug, scaffold_content
from .staging import StagingResult, reset_directory, stage_static_site
from .templates import TemplateAssets
from .state import BuildTracker, ChangeSummary
from .validation import DocumentIssue, DocumentValidationError, IssueSeverity, lint_workspace
from .verify import VerificationReport, verify_site

if TYPE_CHECKING:
    from .gallery import GalleryWorkspace
    from .media.audit import ReferenceUsage
    from .content import ContentDocument

console = Console()
app = typer.Typer(help="SmileCMS static publishing toolkit.")
audit_app = typer.Typer(help="Audit workspace content and media.")
app.add_typer(audit_app, name="audit")

class NewContentType(str, Enum):
    """Kinds of content that can be scaffolded from the CLI."""

    POST = "post"
    GALLERY = "gallery"
    TRACK = "track"


ConfigPathOption = Annotated[
    str,
    typer.Option("--config", "-c", help="Path to configuration file."),
]
TitleOption = Annotated[
    str | None,
    typer.Option("--title", "-t", help="Override the default title derived from the slug."),
]
ForceFlag = Annotated[
    bool,
    typer.Option("--force", "-f", help="Overwrite existing files if they already exist."),
]


@dataclass(slots=True)
class BuildOutputs:
    """Aggregate results from the main build pipeline."""

    report: BuildReport
    manifest_paths: list[Path]
    feed_paths: list[Path]
    gallery_updates: int
    report_path: Path


@dataclass(slots=True)
class StageArtifacts:
    """Outputs collected while staging ancillary assets."""

    stage_result: StagingResult
    article_pages: list[Path]
    gallery_page: Path
    music_page: Path
    music_result: MusicExportResult


@app.command()
def new(  # noqa: PLR0913
    kind: Annotated[
        NewContentType,
        typer.Argument(..., help="Content type to scaffold."),
    ],
    slug: Annotated[
        str,
        typer.Argument(..., help="Slug identifier used for files and directories."),
    ],
    title: TitleOption = None,
    config_path: ConfigPathOption = "smilecms.yml",
    force: ForceFlag = False,
) -> None:
    """Create a new post, gallery, or track using the recommended layout."""
    try:
        normalized_slug = normalize_slug(slug)
    except ScaffoldError as exc:
        console.print(f"[bold red]Cannot scaffold[/]: {exc}")
        raise typer.Exit(code=1) from exc

    config: Config = _load(config_path)

    try:
        result = scaffold_content(
            config=config,
            kind=kind.value,
            slug=normalized_slug,
            title=title,
            force=force,
        )
    except ScaffoldError as exc:
        console.print(f"[bold red]Cannot scaffold[/]: {exc}")
        raise typer.Exit(code=1) from exc

    if normalized_slug != slug:
        console.print(
            f"[bold yellow]Note[/]: slug normalized to '{normalized_slug}'.",
        )

    _print_scaffold_summary(kind, normalized_slug, result)

@app.command()
def lint(
    config_path: ConfigPathOption = "smilecms.yml",
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Treat warnings as errors."),
    ] = False,
) -> None:
    """Run lightweight checks for common content issues."""
    config: Config = _load(config_path)
    report = lint_workspace(config)

    if not report.issues:
        console.print("[bold green]Lint clean[/]: no issues detected.")
        raise typer.Exit()

    for issue in sorted(report.issues, key=_lint_sort_key):
        style = "red" if issue.severity is IssueSeverity.ERROR else "yellow"
        location = issue.source_path
        if issue.pointer:
            location = f"{location} :: {issue.pointer}"
        console.print(f"[bold {style}]{issue.severity.name}[/] {location} - {issue.message}")

    console.print(
        f"[bold blue]Summary[/]: {report.error_count} error(s), {report.warning_count} warning(s) "
        f"across {report.document_count} document(s)."
    )

    exit_code = 0
    if report.error_count > 0 or (strict and report.warning_count > 0):
        exit_code = 1
    raise typer.Exit(code=exit_code)

@app.command()
def build(
    config_path: ConfigPathOption = "smilecms.yml",
    force: ForceFlag = False,
) -> None:
    """Run a full rebuild of site artifacts."""
    config: Config = _load(config_path)
    tracker = BuildTracker(config, Path(config_path))
    fingerprints = tracker.compute_fingerprints()
    change_summary = tracker.summarize_changes(fingerprints)

    _prepare_output_directories(config, change_summary, force)

    gallery_workspace: "GalleryWorkspace" = prepare_gallery_workspace(config)
    documents = _load_build_documents(config, gallery_workspace)

    outputs = _generate_site_artifacts(config, documents, gallery_workspace)

    _print_primary_summary(outputs, config, gallery_workspace)

    stage_artifacts = _stage_static_assets(config, tracker, documents, gallery_workspace)

    _print_stage_summary(config, outputs, stage_artifacts, gallery_workspace)

    tracker.persist(fingerprints, stage_artifacts.stage_result.template_paths)

    _print_accumulated_warnings(outputs.report, gallery_workspace, stage_artifacts.music_result)


def _prepare_output_directories(config: Config, change_summary: ChangeSummary, force: bool) -> None:
    if force:
        console.print(
            "[bold yellow]Force rebuild[/]: clearing output directories before regenerating."
        )
        reset_directory(config.output_dir)
        reset_directory(config.media_processing.output_dir)
        return

    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.media_processing.output_dir.mkdir(parents=True, exist_ok=True)

    if change_summary.first_run:
        console.print(
            "[bold yellow]Incremental build[/]: initializing cache; no previous state detected."
        )
        return

    if change_summary.changed_keys:
        categories = ", ".join(sorted(change_summary.changed_keys))
        console.print(
            "[bold green]Incremental build[/]: changes detected in "
            f"{categories}."
        )
        return

    console.print(
        "[bold blue]Incremental build[/]: no input changes detected; "
        "reusing cached artifacts."
    )


def _load_build_documents(
    config: Config,
    gallery_workspace: "GalleryWorkspace",
) -> list["ContentDocument"]:
    try:
        return load_documents(config, gallery_workspace=gallery_workspace)
    except DocumentValidationError as error:
        console.print(f"[bold red]Validation failed[/]: {error}")
        raise typer.Exit(code=1) from error


def _generate_site_artifacts(
    config: Config,
    documents: Sequence["ContentDocument"],
    gallery_workspace: "GalleryWorkspace",
) -> BuildOutputs:
    start = time.perf_counter()

    media_plan = collect_media_plan(documents, config)
    media_result = process_media_plan(media_plan, config)
    apply_variants_to_documents(documents, media_result.variants)
    updated_gallery = apply_gallery_derivatives(gallery_workspace, media_result, config)

    pages = ManifestGenerator().build_pages(documents, prefix="content")
    manifest_paths = write_manifest_pages(pages, config.output_dir / "manifests")

    report = assemble_report(
        project=config.project_name,
        duration_seconds=time.perf_counter() - start,
        documents=build_document_stats(documents),
        manifests=build_manifest_stats(pages),
        media=build_media_stats(media_plan, media_result),
    )
    report_path = write_report(report, config.output_dir)

    return BuildOutputs(
        report=report,
        manifest_paths=manifest_paths,
        feed_paths=generate_feeds(config, pages),
        gallery_updates=updated_gallery,
        report_path=report_path,
    )


def _print_primary_summary(
    outputs: BuildOutputs,
    config: Config,
    gallery_workspace: "GalleryWorkspace",
) -> None:
    report = outputs.report
    documents = report.documents
    manifests = report.manifests

    console.print(
        "[bold green]Documents[/]: "
        f"{documents.total} "
        f"(published {documents.published}, "
        f"drafts {documents.drafts}, "
        f"archived {documents.archived})"
    )
    console.print(
        "[bold green]Manifests[/]: "
        f"{manifests.pages} page(s) with {manifests.items} item(s); "
        f"written {len(outputs.manifest_paths)} file(s) to "
        f"{_display_path(config.output_dir / 'manifests')}"
    )

    if outputs.feed_paths:
        feed_locations = ", ".join(_display_path(path) for path in outputs.feed_paths)
        console.print(
            "[bold green]Feeds[/]: generated syndication feeds at "
            f"{feed_locations}"
        )

    stats = report.media
    media_line = (
        "[bold green]Media[/]: "
        f"{stats.assets_processed}/{stats.assets_planned} asset(s) produced "
        f"{stats.variants_generated} variant(s); "
        f"{stats.assets_copied} copied"
    )
    if stats.assets_reused:
        media_line += f", {stats.assets_reused} reused"
    media_line += ". "
    media_line += (
        f"{stats.tasks_processed}/{stats.tasks_planned} image task(s) rendered"
    )
    if stats.tasks_reused:
        media_line += f", {stats.tasks_reused} reused"
    media_line += f" ({stats.tasks_skipped} skipped)"
    if stats.artifacts_pruned:
        media_line += f"; removed {stats.artifacts_pruned} stale file(s)"
    console.print(media_line)

    console.print(
        "[bold green]Gallery[/]: "
        f"{gallery_workspace.collection_count()} collection(s) with "
        f"{gallery_workspace.image_count()} image(s); "
        f"{len(gallery_workspace.collection_writes)} collection sidecar(s) "
        f"and {len(gallery_workspace.image_writes)} image sidecar(s) updated; "
        f"{outputs.gallery_updates} derivative mapping(s) refreshed"
    )


def _stage_static_assets(
    config: Config,
    tracker: BuildTracker,
    documents: Sequence["ContentDocument"],
    gallery_workspace: "GalleryWorkspace",
) -> StageArtifacts:
    previous_templates = tracker.previous_template_paths or None
    stage_result = stage_static_site(
        config,
        previous_template_paths=previous_templates,
    )
    template_assets = TemplateAssets(config)
    article_pages = write_article_pages(documents, config, assets=template_assets)
    gallery_page = write_gallery_page(config, template_assets)
    music_page = write_music_page(config, template_assets)
    export_gallery_datasets(gallery_workspace, config)
    music_result = export_music_catalog(documents, config)
    return StageArtifacts(
        stage_result=stage_result,
        article_pages=article_pages,
        gallery_page=gallery_page,
        music_page=music_page,
        music_result=music_result,
    )


def _print_stage_summary(
    config: Config,
    outputs: BuildOutputs,
    stage_artifacts: StageArtifacts,
    gallery_workspace: "GalleryWorkspace",
) -> None:
    stage_result = stage_artifacts.stage_result
    if stage_result.total:
        console.print(
            "[bold green]Static bundle[/]: "
            f"staged {stage_result.total} item(s) into {_display_path(config.output_dir)}"
        )
    else:
        console.print(
            "[bold yellow]Static bundle[/]: "
            f"no template assets found at {_display_path(config.templates_dir)}"
        )
    if stage_result.removed_templates:
        console.print(
            "[bold yellow]Static bundle[/]: "
            f"removed {len(stage_result.removed_templates)} stale template asset(s)"
        )

    if stage_artifacts.article_pages:
        console.print(
            "[bold green]Articles[/]: "
            f"rendered {len(stage_artifacts.article_pages)} page(s) in "
            f"{_display_path(config.output_dir / 'posts')}"
        )
    console.print(
        "[bold green]Gallery page[/]: "
        f"rendered {_display_path(stage_artifacts.gallery_page)}"
    )
    console.print(
        "[bold green]Music page[/]: "
        f"rendered {_display_path(stage_artifacts.music_page)}"
    )

    if gallery_workspace.data_writes:
        console.print(
            "[bold green]Gallery data[/]: "
            f"wrote {len(gallery_workspace.data_writes)} file(s) to "
            f"{_display_path(config.output_dir / config.gallery.data_subdir)}"
        )

    if stage_artifacts.music_result.written:
        console.print(
            "[bold green]Music catalog[/]: "
            f"exported {stage_artifacts.music_result.tracks} track(s); wrote "
            f"{len(stage_artifacts.music_result.written)} file(s) to "
            f"{_display_path(config.output_dir / config.music.data_subdir)}"
        )

    console.print(
        "[bold green]Report[/]: "
        f"{_display_path(outputs.report_path)} "
        f"(duration {outputs.report.duration_seconds:.2f}s)"
    )


def _print_accumulated_warnings(
    report: BuildReport,
    gallery_workspace: "GalleryWorkspace",
    music_result: MusicExportResult,
) -> None:
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
def verify(
    config_path: ConfigPathOption = "smilecms.yml",
    html_validation: Annotated[
        bool,
        typer.Option(
            "--html-validation/--no-html-validation",
            help="Run HTML5 validation on rendered output.",
        ),
    ] = True,
    js_validation: Annotated[
        bool,
        typer.Option(
            "--js-validation/--no-js-validation",
            help="Run JavaScript validation on rendered output.",
        ),
    ] = True,
    report_path: Annotated[
        str | None,
        typer.Option(
            "--report",
            "-r",
            help="Optional path to write a text report summarizing verification findings.",
        ),
    ] = None,
) -> None:
    """Scan the generated site bundle for missing links or assets."""
    config: Config = _load(config_path)
    output_dir = Path(config.output_dir)

    if not output_dir.exists():
        console.print(f"[bold red]Site directory not found[/]: {_display_path(output_dir)}")
        raise typer.Exit(code=1)

    console.print(f"[bold blue]Verifying[/]: scanning HTML files under {_display_path(output_dir)}")
    report = verify_site(output_dir)
    _print_verification_report(report)

    html_report: HtmlValidationReport | None = None
    js_report: JsValidationReport | None = None
    if html_validation:
        console.print(
            f"[bold blue]HTML validation[/]: validating {_display_path(output_dir)} with html5validator"
        )
        try:
            html_report = validate_html(output_dir)
        except HtmlValidatorUnavailableError as exc:
            console.print(f"[bold yellow]HTML validation skipped[/]: {exc}")
        except HtmlValidatorError as exc:
            console.print(f"[bold red]HTML validation failed[/]: {exc}")
            raise typer.Exit(code=1) from exc
        else:
            _print_html_validation_report(html_report)

    if js_validation:
        console.print(
            f"[bold blue]JavaScript validation[/]: parsing scripts under {_display_path(output_dir)}"
        )
        try:
            js_report = validate_javascript(output_dir)
        except JsValidatorUnavailableError as exc:
            console.print(f"[bold yellow]JavaScript validation skipped[/]: {exc}")
        except JsValidatorError as exc:
            console.print(f"[bold red]JavaScript validation failed[/]: {exc}")
            raise typer.Exit(code=1) from exc
        else:
            _print_js_validation_report(js_report)

    if report_path:
        target = Path(report_path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                _render_verification_text(report, output_dir, html_report, js_report),
                encoding="utf-8",
            )
            console.print(f"[bold green]Report written[/]: {_display_path(target)}")
        except OSError as exc:
            console.print(f"[bold red]Failed to write report[/]: {exc}")
            raise typer.Exit(code=1) from exc

    exit_code = 1 if report.error_count > 0 else 0
    if html_report and html_report.error_count > 0:
        exit_code = 1
    if js_report and js_report.error_count > 0:
        exit_code = 1
    raise typer.Exit(code=exit_code)


@audit_app.command("media")
def audit_media_command(
    config_path: ConfigPathOption = "smilecms.yml",
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Emit machine-readable JSON instead of human formatted output.",
        ),
    ] = False,
) -> None:
    """Inspect media references and files for missing or misplaced assets."""
    config: Config = _load(config_path)
    documents = load_documents(config)
    result = audit_media(documents, config)
    if json_output:
        console.print_json(data=_media_audit_payload(result))
        return
    _print_media_audit(result)


@app.command()
def preview(
    config_path: ConfigPathOption = "smilecms.yml",
    host: Annotated[
        str,
        typer.Option("--host", help="Host interface to bind the preview server."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Port for the preview server."),
    ] = 8000,
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open-browser/--no-open-browser",
            help="Automatically open the site in a browser after starting.",
        ),
    ] = False,
) -> None:
    """Serve the generated site directory with a simple HTTP server."""
    config: Config = _load(config_path)
    if port < 0 or port > 65535:
        raise typer.BadParameter("Port must be between 0 and 65535.")

    output_dir = Path(config.output_dir)
    if not output_dir.exists():
        console.print(f"[bold red]Site output not found[/]: {output_dir}")
        console.print("Run 'smilecms build' to generate the static bundle before previewing.")
        raise typer.Exit(code=1)

    if not any(output_dir.iterdir()):
        console.print(
            "[bold yellow]Warning[/]: "
            f"{output_dir} is empty. Run 'smilecms build' to populate the site."
        )

    handler = _make_request_handler(output_dir)

    try:
        with _serve(host, port, handler) as server:
            raw_host = server.server_address[0]
            bound_host = (
                raw_host.decode("utf-8", "ignore") if isinstance(raw_host, bytes) else str(raw_host)
            )
            bound_port = int(server.server_address[1])
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
    config_path: ConfigPathOption = "smilecms.yml",
    include_cache: Annotated[
        bool,
        typer.Option("--cache", help="Also remove the configured cache directory."),
    ] = False,
) -> None:
    """Remove generated artifacts (site bundle, media derivatives, and optional cache)."""
    config: Config = _load(config_path)
    media_processing: MediaProcessingConfig = cast(
        MediaProcessingConfig,
        getattr(config, "media_processing"),
    )
    targets: list[tuple[str, Path]] = [
        ("site output", Path(config.output_dir)),
        ("media derivatives", Path(media_processing.output_dir)),
    ]
    if include_cache:
        targets.append(("cache", Path(config.cache_dir)))

    removed = 0
    for label, path in targets:
        if path.exists():
            console.print(f"[bold green]Removing[/]: {label} ({path})")
            _remove_path(path)
            removed += 1
        else:
            console.print(f"[bold yellow]Skipping[/]: {label} ({path}) not found")

    noun = "directory" if removed == 1 else "directories"
    console.print(f"[bold green]Clean complete[/]: removed {removed} {noun}.")


def _print_scaffold_summary(kind: NewContentType, slug: str, result: ScaffoldResult) -> None:
    console.print(f"[bold green]Scaffold ready[/]: {kind.value} '{slug}'")

    for path in result.created:
        console.print(f"- {_display_path(path)} (new)")
    for path in result.updated:
        console.print(f"- {_display_path(path)} (updated)")

    if result.notes:
        console.print("[bold blue]Next steps[/]:")
        for note in result.notes:
            console.print(f"- {note}")


def _lint_sort_key(issue: DocumentIssue) -> tuple[int, str, str]:
    severity_order = 0 if issue.severity is IssueSeverity.ERROR else 1
    pointer = issue.pointer or ""
    return (severity_order, issue.source_path, pointer)


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


def _media_audit_payload(result: MediaAuditResult) -> dict[str, object]:
    def serialize_usage(path: str, usage: "ReferenceUsage") -> dict[str, object]:
        payload: dict[str, object] = {
            "path": path,
            "documents": sorted(usage.documents),
        }
        if usage.roles:
            payload["roles"] = sorted(usage.roles)
        if usage.expected_path:
            payload["expected_path"] = usage.expected_path.as_posix()
        return payload

    payload: dict[str, object] = {
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
            serialize_usage(
                path,
                result.missing_references[path],
            )
            for path in sorted(result.missing_references)
        ],
        "out_of_bounds_references": [
            serialize_usage(
                path,
                result.out_of_bounds_references[path],
            )
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


def _print_verification_report(report: VerificationReport) -> None:
    if not report.issues:
        console.print(
            "[bold green]Verification complete[/]: "
            f"{report.scanned_files} HTML file(s) scanned; no issues found."
        )
        return

    console.print(
        "[bold red]Verification issues[/]: "
        f"{len(report.issues)} issue(s) detected across {report.scanned_files} file(s)."
    )
    for issue in report.issues:
        color = "yellow" if issue.kind == "warning" else "red"
        console.print(
            f"[bold {color}]{issue.kind}[/] "
            f"{_display_path(issue.source)} -> {issue.target} :: {issue.message}"
        )


def _render_verification_text(
    report: VerificationReport,
    output_dir: Path,
    html_report: HtmlValidationReport | None = None,
    js_report: JsValidationReport | None = None,
) -> str:
    lines = [
        "SmileCMS site verification report",
        f"Output directory: {output_dir.resolve().as_posix()}",
        f"HTML files scanned: {report.scanned_files}",
        f"Issues detected: {len(report.issues)}",
        "",
    ]
    if not report.issues:
        lines.append("No issues detected.")
    else:
        for issue in report.issues:
            lines.append(
                f"- [{issue.kind}] "
                f"{issue.source.resolve().as_posix()} -> {issue.target}: {issue.message}"
            )
    lines.append("")
    if html_report:
        lines.append("HTML validation summary")
        lines.append(f"Files validated: {html_report.scanned_files}")
        lines.append(f"Errors: {html_report.error_count}")
        lines.append(f"Warnings: {html_report.warning_count}")
        if html_report.issues:
            lines.append("")
            for html_issue in html_report.issues:
                location = html_issue.location()
                location_text = f":{location}" if location else ""
                lines.append(
                    f"- [{html_issue.severity}] "
                    f"{html_issue.file.resolve().as_posix()}{location_text}: {html_issue.message}"
                )
    if js_report:
        lines.append("")
        lines.append("JavaScript validation summary")
        lines.append(f"Files validated: {js_report.scanned_files}")
        lines.append(f"Errors: {js_report.error_count}")
        lines.append(f"Warnings: {js_report.warning_count}")
        if js_report.issues:
            lines.append("")
            for js_issue in js_report.issues:
                location = js_issue.location()
                location_text = f":{location}" if location else ""
                lines.append(
                    f"- [{js_issue.severity}] "
                    f"{js_issue.file.resolve().as_posix()}{location_text}: {js_issue.message}"
                )
    lines.append("")
    return "\n".join(lines)


def _print_html_validation_report(report: HtmlValidationReport) -> None:
    if not report.issues:
        console.print(
            "[bold green]HTML validation[/]: "
            f"{report.scanned_files} HTML file(s) validated; no issues found."
        )
        return

    console.print(
        "[bold red]HTML validation issues[/]: "
        f"{report.error_count} error(s), {report.warning_count} warning(s) "
        f"across {report.scanned_files} file(s)."
    )
    for html_issue in report.issues:
        color = "red" if html_issue.severity == "error" else "yellow"
        if html_issue.severity not in {"error", "warning"}:
            color = "blue"
        location = html_issue.location()
        location_text = f":{location}" if location else ""
        console.print(
            f"[bold {color}]{html_issue.severity}[/] "
            f"{_display_path(html_issue.file)}{location_text} :: {html_issue.message}"
        )


def _print_js_validation_report(report: JsValidationReport) -> None:
    if not report.issues:
        console.print(
            "[bold green]JavaScript validation[/]: "
            f"{report.scanned_files} script(s) validated; no issues found."
        )
        return

    console.print(
        "[bold red]JavaScript validation issues[/]: "
        f"{report.error_count} error(s), {report.warning_count} warning(s) "
        f"across {report.scanned_files} file(s)."
    )
    for js_issue in report.issues:
        color = "red" if js_issue.severity == "error" else "yellow"
        if js_issue.severity not in {"error", "warning"}:
            color = "blue"
        location = js_issue.location()
        location_text = f":{location}" if location else ""
        console.print(
            f"[bold {color}]{js_issue.severity}[/] "
            f"{_display_path(js_issue.file)}{location_text} :: {js_issue.message}"
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


def _make_request_handler(directory: Path) -> type[SimpleHTTPRequestHandler]:
    directory_path = str(directory)

    class PreviewRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=directory_path, **kwargs)

    return PreviewRequestHandler


@contextlib.contextmanager
def _serve(
    host: str,
    port: int,
    handler: type[SimpleHTTPRequestHandler],
) -> Iterator[ThreadingHTTPServer]:
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
