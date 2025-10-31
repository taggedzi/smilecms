"""Service layer for SmileCMS GUI.

This module exposes high-level operations for the GUI while reusing existing
library functions. It avoids calling the Typer CLI and returns structured
results that are easy to present in the UI.
"""

from __future__ import annotations

import difflib
import json
import os
import sys
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence, Literal

import yaml

from .articles import write_article_pages
from .config import Config, MediaProcessingConfig, load_config
from .feeds import generate_feeds
from .gallery import (
    GalleryWorkspace,
    apply_derivatives as apply_gallery_derivatives,
    export_datasets as export_gallery_datasets,
    prepare_workspace as prepare_gallery_workspace,
)
from .htmlvalidate import (
    HtmlValidationReport,
    HtmlValidatorError,
    HtmlValidatorUnavailableError,
    validate_html,
)
from .ingest import load_documents
from .jsvalidate import (
    JsValidationReport,
    JsValidatorError,
    JsValidatorUnavailableError,
    validate_javascript,
)
from .manifests import ManifestGenerator, write_manifest_pages
from .media import apply_variants_to_documents, collect_media_plan, process_media_plan
from .music import MusicExportResult, export_music_catalog
from .pages import write_error_pages, write_gallery_page, write_music_page
from .preview_server import PreviewServerHandle, start_preview, stop_preview
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
from .state import BuildTracker
from .validation import DocumentValidationError
from .verify import VerificationReport, verify_site


# -------------------------
# Data structures
# -------------------------


@dataclass(slots=True)
class MRU:
    paths: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class BuildOptions:
    force: bool = False
    refresh_gallery: bool = False


@dataclass(slots=True)
class BuildResult:
    report: BuildReport
    manifest_paths: list[Path]
    feed_paths: list[Path]
    gallery_updates: int
    report_path: Path
    stage_result: StagingResult
    article_pages: list[Path]
    gallery_page: Path | None
    music_page: Path | None
    music_result: MusicExportResult | None
    error_pages: list[Path]


@dataclass(slots=True)
class EnvStatus:
    python_version: str
    executable: str
    venv: str | None
    node_path: str | None
    node_version: str | None
    htmlvalidator_available: bool
    htmlvalidator_error: str | None
    js_available: bool
    js_error: str | None
    torch_available: bool
    cuda_available: bool
    mps_available: bool
    huggingface_available: bool
    spacy_available: bool
    spacy_model: str | None
    hf_cache_dir: Path | None


# -------------------------
# Project + MRU helpers
# -------------------------


def _app_data_dir() -> Path:
    if sys.platform.startswith("win"):
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
        return Path(root) / "SmileCMS"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/SmileCMS"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "SmileCMS"


def _mru_path() -> Path:
    return _app_data_dir() / "mru.json"


def get_mru(max_items: int = 10) -> MRU:
    path = _mru_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = [Path(p) for p in data.get("projects", [])]
        return MRU(paths=items[:max_items])
    except Exception:
        return MRU()


def add_mru(project_dir: Path, max_items: int = 10) -> None:
    mru = get_mru(max_items=max_items)
    proj = project_dir.resolve()
    items = [p for p in mru.paths if p != proj]
    items.insert(0, proj)
    data = {"projects": [str(p) for p in items[:max_items]]}
    out = _mru_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")


def remove_mru(project_dir: Path) -> None:
    mru = get_mru()
    items = [p for p in mru.paths if p.resolve() != project_dir.resolve()]
    data = {"projects": [str(p) for p in items]}
    out = _mru_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")


def discover_project(path: Path) -> dict[str, Any]:
    p = path.resolve()
    config_file = p / "smilecms.yml"
    exists = config_file.exists()
    return {"config_path": config_file, "exists": exists, "errors": []}


# -------------------------
# Configuration helpers
# -------------------------


def load_config_with_text(path_or_dir: Path) -> tuple[Config, Path, str]:
    cfg = load_config(path_or_dir)
    # Determine actual config file path
    candidate = Path(path_or_dir)
    config_path = candidate / "smilecms.yml" if candidate.is_dir() else candidate
    text = ""
    try:
        text = config_path.read_text(encoding="utf-8")
    except Exception:
        text = yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False)
    return cfg, config_path, text


def render_config_yaml(cfg: Config) -> str:
    # Dump model as YAML with stable key order (match model order)
    data = cfg.model_dump(mode="json")
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def diff_yaml(before: str, after: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(), fromfile="before", tofile="after", lineterm=""
    )
    return "\n".join(diff)


def save_config(cfg: Config, config_path: Path, backup: bool = True) -> dict[str, Path | None]:
    config_path = config_path.resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if backup and config_path.exists():
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = config_path.with_suffix(config_path.suffix + f".{stamp}.bak")
        backup_path.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    text = render_config_yaml(cfg)
    config_path.write_text(text, encoding="utf-8")
    return {"saved_path": config_path, "backup_path": backup_path}


# -------------------------
# Scaffold new content
# -------------------------


def scaffold(
    kind: Literal["post", "gallery", "track"],
    slug: str,
    *,
    title: str | None,
    force: bool,
    config_path: Path,
) -> ScaffoldResult:
    normalized = normalize_slug(slug)
    cfg = load_config(config_path)
    return scaffold_content(config=cfg, kind=kind, slug=normalized, title=title, force=force)


# -------------------------
# Build pipeline (GUI)
# -------------------------


def _prepare_outputs(cfg: Config, force: bool, log: Callable[[str], None]) -> None:
    if force:
        log("Force rebuild: clearing output directories before regenerating.")
        reset_directory(cfg.output_dir)
        reset_directory(cfg.media_processing.output_dir)
    else:
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        cfg.media_processing.output_dir.mkdir(parents=True, exist_ok=True)


def build(
    cfg: Config,
    *,
    config_file_path: Path,
    options: BuildOptions,
    progress_cb: Callable[[str, int, int], None] | None = None,
    log_cb: Callable[[str], None] | None = None,
) -> BuildResult:
    log = log_cb or (lambda msg: None)

    # Optional: adjust Pillow decompression bomb guard if configured
    try:
        from PIL import Image

        limit = getattr(cfg.media_processing, "decompression_bomb_limit", None)
        if limit is not None:
            if int(limit) <= 0:
                Image.MAX_IMAGE_PIXELS = None
            else:
                Image.MAX_IMAGE_PIXELS = int(limit)
    except Exception:
        pass

    tracker = BuildTracker(cfg, Path(config_file_path))
    fingerprints = tracker.compute_fingerprints()

    _prepare_outputs(cfg, options.force, log)

    if cfg.gallery.enabled:
        gallery_workspace = prepare_gallery_workspace(cfg, refresh=options.refresh_gallery)
    else:
        gallery_workspace = GalleryWorkspace(root=cfg.gallery.source_dir)

    try:
        documents = load_documents(cfg, gallery_workspace=gallery_workspace)
    except DocumentValidationError as exc:
        raise RuntimeError(f"Validation failed: {exc}") from exc

    # Media plan + processing
    media_plan = collect_media_plan(documents, cfg)

    deriv_total = len(media_plan.tasks)
    asset_total = len(media_plan.static_assets)

    def _on_progress(kind: str) -> None:
        if progress_cb is None:
            return
        if kind == "derivative":
            progress_cb("Derivatives", 1, deriv_total)
        elif kind == "asset":
            progress_cb("Assets", 1, asset_total)

    media_result = process_media_plan(media_plan, cfg, on_progress=_on_progress)
    apply_variants_to_documents(documents, media_result.variants)

    updated_gallery = 0
    if cfg.gallery.enabled:
        updated_gallery = apply_gallery_derivatives(
            gallery_workspace, media_result, cfg, refresh=options.refresh_gallery
        )

    pages = ManifestGenerator().build_pages(documents, prefix="content")
    manifest_paths = write_manifest_pages(pages, cfg.output_dir / "manifests")

    report = assemble_report(
        project=cfg.project_name,
        duration_seconds=0.0,  # timing not critical for GUI summary
        documents=build_document_stats(documents),
        manifests=build_manifest_stats(pages),
        media=build_media_stats(media_plan, media_result),
    )
    report_path = write_report(report, cfg.output_dir)

    # Stage static assets and pages
    previous_templates = tracker.previous_template_paths or None
    stage_result = stage_static_site(cfg, previous_template_paths=previous_templates)
    from .templates import TemplateAssets

    template_assets = TemplateAssets(cfg)
    template_assets.write_site_config()
    article_pages = write_article_pages(documents, cfg, assets=template_assets)
    gallery_page: Path | None = None
    music_page: Path | None = None
    music_result: MusicExportResult | None = None
    if cfg.gallery.enabled:
        gallery_page = write_gallery_page(cfg, template_assets)
        export_gallery_datasets(gallery_workspace, cfg)
    else:
        # prune gallery outputs if disabled
        _prune(cfg.output_dir / "gallery")
        _prune(cfg.output_dir / cfg.gallery.data_subdir)
    if cfg.music.enabled:
        music_page = write_music_page(cfg, template_assets)
        music_result = export_music_catalog(documents, cfg)
    else:
        _prune(cfg.output_dir / "music")
        _prune(cfg.output_dir / "data/music")
    error_pages = write_error_pages(cfg, template_assets)

    tracker.persist(fingerprints, stage_result.template_paths)

    return BuildResult(
        report=report,
        manifest_paths=manifest_paths,
        feed_paths=generate_feeds(cfg, pages),
        gallery_updates=updated_gallery,
        report_path=report_path,
        stage_result=stage_result,
        article_pages=article_pages,
        gallery_page=gallery_page,
        music_page=music_page,
        music_result=music_result,
        error_pages=error_pages,
    )


def _prune(path: Path) -> None:
    try:
        if path.exists():
            if path.is_dir():
                import shutil

                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
    except Exception:
        pass


# -------------------------
# Verify + audit
# -------------------------


def verify_links(cfg: Config) -> VerificationReport:
    return verify_site(Path(cfg.output_dir))


def validate_html_safe(cfg: Config) -> HtmlValidationReport | tuple[None, str]:
    try:
        return validate_html(Path(cfg.output_dir))
    except HtmlValidatorUnavailableError as exc:
        return (None, str(exc))
    except HtmlValidatorError as exc:
        # surface error text to UI
        raise RuntimeError(str(exc)) from exc


def validate_js_safe(cfg: Config) -> JsValidationReport | tuple[None, str]:
    try:
        return validate_javascript(Path(cfg.output_dir))
    except JsValidatorUnavailableError as exc:
        return (None, str(exc))
    except JsValidatorError as exc:
        raise RuntimeError(str(exc)) from exc


def render_verification_text(
    report: VerificationReport,
    output_dir: Path,
    html_report: HtmlValidationReport | None = None,
    js_report: JsValidationReport | None = None,
) -> str:
    lines: list[str] = [
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
                f"- [{issue.kind}] {issue.source.resolve().as_posix()} -> {issue.target}: {issue.message}"
            )
    if html_report:
        lines.extend([
            "",
            "HTML validation summary",
            f"Files validated: {html_report.scanned_files}",
            f"Errors: {html_report.error_count}",
            f"Warnings: {html_report.warning_count}",
        ])
        for html_issue in html_report.issues:
            location = html_issue.location()
            suffix = f":{location}" if location else ""
            lines.append(
                f"- [{html_issue.severity}] {html_issue.file.resolve().as_posix()}{suffix}: {html_issue.message}"
            )
    if js_report:
        lines.extend([
            "",
            "JavaScript validation summary",
            f"Files validated: {js_report.scanned_files}",
            f"Errors: {js_report.error_count}",
            f"Warnings: {js_report.warning_count}",
        ])
        for js_issue in js_report.issues:
            location = js_issue.location()
            suffix = f":{location}" if location else ""
            lines.append(
                f"- [{js_issue.severity}] {js_issue.file.resolve().as_posix()}{suffix}: {js_issue.message}"
            )
    return "\n".join(lines)


def audit_media_json_payload(result: Any) -> dict[str, object]:
    # Reproduce the CLI's JSON payload structure for media audit results.
    def serialize_usage(path: str, usage: Any) -> dict[str, object]:
        payload: dict[str, object] = {
            "path": path,
            "documents": sorted(usage.documents),
        }
        if usage.roles:
            payload["roles"] = sorted(usage.roles)
        if usage.expected_path:
            payload["expected_path"] = usage.expected_path.as_posix()
        return payload

    return {
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
            serialize_usage(path, result.missing_references[path])
            for path in sorted(result.missing_references)
        ],
        "out_of_bounds_references": [
            serialize_usage(path, result.out_of_bounds_references[path])
            for path in sorted(result.out_of_bounds_references)
        ],
        "orphan_assets": [
            {"path": path, "source_path": result.orphan_files[path].as_posix()}
            for path in sorted(result.orphan_files)
        ],
        "stray_assets": [
            {"path": result.stray_files[key].as_posix()} for key in sorted(result.stray_files)
        ],
    }


# -------------------------
# Preview control
# -------------------------


def start_preview_server(cfg: Config, host: str = "127.0.0.1", port: int = 8000) -> PreviewServerHandle:
    return start_preview(Path(cfg.output_dir), host=host, port=port, max_attempts=20)


def stop_preview_server(handle: PreviewServerHandle | None) -> None:
    stop_preview(handle)


# -------------------------
# Environment checks
# -------------------------


def check_environment(cfg: Config | None = None) -> EnvStatus:
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    executable = sys.executable
    venv = os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_PREFIX")

    # html5validator
    html_ok = False
    html_err: str | None = None
    try:
        import importlib

        importlib.import_module("html5validator.cli")
        html_ok = True
    except Exception as exc:
        html_ok = False
        html_err = str(exc)

    # node --version
    node_path: str | None = None
    node_version: str | None = None
    js_ok = False
    js_err: str | None = None
    try:
        import shutil
        import subprocess

        node_path = shutil.which("node")
        if node_path:
            cp = subprocess.run([node_path, "--version"], capture_output=True, text=True, check=False)
            ver = (cp.stdout or cp.stderr or "").strip()
            node_version = ver
            # Expect v14+
            txt = ver[1:] if ver.startswith("v") else ver
            parts = txt.split(".")
            major = int(parts[0]) if parts and parts[0].isdigit() else 0
            js_ok = major >= 14
            if not js_ok:
                js_err = f"Node {ver} detected; require >= 14"
        else:
            js_err = "Node.js not found in PATH"
    except Exception as exc:
        js_ok = False
        js_err = str(exc)

    # ML stack
    torch_avail = False
    cuda_avail = False
    mps_avail = False
    hf_avail = False
    spacy_avail = False
    spacy_model: str | None = None
    try:
        import torch

        torch_avail = True
        cuda_avail = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
        try:
            from torch.backends import mps as torch_mps

            mps_avail = bool(torch_mps.is_available())
        except Exception:
            mps_avail = False
    except Exception:
        torch_avail = False
    try:
        import huggingface_hub

        hf_avail = True
    except Exception:
        hf_avail = False
    try:
        import spacy

        spacy_avail = True
        try:
            # Probe a common model name
            import importlib

            importlib.import_module("en_core_web_sm")
            spacy_model = "en_core_web_sm"
        except Exception:
            spacy_model = None
    except Exception:
        spacy_avail = False

    # Hugging Face cache location
    hf_cache: Path | None = None
    try:
        home = Path.home()
        hf_home = os.environ.get("HF_HOME")
        hf_hub_cache = os.environ.get("HF_HUB_CACHE")
        if hf_hub_cache:
            hf_cache = Path(hf_hub_cache)
        elif hf_home:
            hf_cache = Path(hf_home) / "hub"
        else:
            # default
            hf_cache = home / ".cache/huggingface/hub"
    except Exception:
        hf_cache = None

    return EnvStatus(
        python_version=py_ver,
        executable=executable,
        venv=venv,
        node_path=node_path,
        node_version=node_version,
        htmlvalidator_available=html_ok,
        htmlvalidator_error=html_err,
        js_available=js_ok,
        js_error=js_err,
        torch_available=torch_avail,
        cuda_available=cuda_avail,
        mps_available=mps_avail,
        huggingface_available=hf_avail,
        spacy_available=spacy_avail,
        spacy_model=spacy_model,
        hf_cache_dir=hf_cache,
    )


def open_in_browser(url: str) -> None:
    webbrowser.open(url)


# -------------------------
# Clean (guarded)
# -------------------------


def clean(cfg: Config, include_cache: bool = False) -> dict[str, list[tuple[str, Path]]]:
    targets: list[tuple[str, Path]] = [
        ("site output", Path(cfg.output_dir)),
        ("media derivatives", Path(cfg.media_processing.output_dir)),
    ]
    if include_cache:
        targets.append(("cache", Path(cfg.cache_dir)))

    removed: list[tuple[str, Path]] = []
    skipped: list[tuple[str, Path]] = []
    for label, path in targets:
        try:
            if path.exists():
                if path.is_dir():
                    import shutil

                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
                removed.append((label, path))
            else:
                skipped.append((label, path))
        except Exception:
            # If removal fails, treat as skipped; GUI can surface errors separately
            skipped.append((label, path))
    return {"removed": removed, "skipped": skipped}


# -------------------------
# Theme management (examples -> project)
# -------------------------


def _examples_web_dir() -> Path | None:
    # Attempt to locate the repo examples directory relative to this file.
    here = Path(__file__).resolve()
    # .../src/gui_service.py -> repo_root/src -> repo_root
    repo_root = here.parent.parent
    candidates = [
        repo_root / "examples" / "demo-site" / "web",
    ]
    for cand in candidates:
        if cand.exists() and cand.is_dir():
            return cand
    return None


def list_stock_themes() -> dict[str, Path]:
    base = _examples_web_dir()
    if not base:
        return {}
    themes: dict[str, Path] = {}
    try:
        for child in base.iterdir():
            if child.is_dir():
                themes[child.name] = child
    except OSError:
        pass
    return themes


def install_stock_theme(
    config_path: Path,
    theme_folder_name: str,
    *,
    overwrite: bool = False,
) -> dict[str, Path | Config]:
    """Copy a stock theme from examples into the project's templates_dir and update site_theme.

    Returns a dict containing installed_path, updated_config, updated_config_path.
    """
    stock = list_stock_themes()
    if theme_folder_name not in stock:
        raise FileNotFoundError(f"Theme '{theme_folder_name}' not found in examples.")
    cfg = load_config(config_path)
    source = stock[theme_folder_name]
    dest = Path(cfg.templates_dir) / theme_folder_name

    import shutil

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Python 3.11+ supports dirs_exist_ok
    shutil.copytree(source, dest, dirs_exist_ok=overwrite)

    # Update config to point at the selected theme
    cfg.site_theme = theme_folder_name
    save_config(cfg, Path(config_path), backup=True)
    return {"installed_path": dest, "updated_config": cfg, "updated_config_path": Path(config_path)}


def list_installed_themes(cfg: Config) -> list[str]:
    """List theme folder names available under the project's templates_dir."""
    themes: list[str] = []
    root = Path(cfg.templates_dir)
    try:
        if root.exists():
            for child in root.iterdir():
                if child.is_dir():
                    themes.append(child.name)
    except OSError:
        pass
    return sorted(themes)


def set_site_theme(config_path: Path, theme_name: str) -> Config:
    """Update site_theme in smilecms.yml and create a .bak."""
    cfg = load_config(config_path)
    cfg.site_theme = theme_name
    save_config(cfg, Path(config_path), backup=True)
    return cfg
