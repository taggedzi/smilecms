# SmileCMS Architecture & Coding Standards

## System Overview
- SmileCMS is a Python 3.11+ static publishing pipeline that ingests Markdown, YAML sidecars, and raw media to produce a fully static bundle in `site/`.
- The CLI (`src/cli.py`) is built with Typer and orchestrates content ingest, derivative generation, manifest export, HTML rendering, and verification. Every command is expected to be idempotent and safe to re-run.
- The project favors deterministic builds: all source content lives in-repo (`content/`, `media/`, `web/`), and the generator never mutates originals.

## Repository Layout
- `src/`: core pipeline package (ingest, media processing, manifests, gallery, music, reporting, verification).
- `content/`: Markdown posts and shared article media (`content/media/`).
- `media/`: raw gallery collections (`image_gallery_raw/`), music tracks (`music_collection/`), and derived assets output (`derived/`).
- `site/`: generated static site (HTML, CSS/JS bundles, JSON feeds, manifest datasets).
- `web/`: static front-end shell (HTML templates, vanilla JS renderers, CSS tokens/styles, site config).
- `tests/`: pytest suite covering CLI flows, media pipelines, manifest generation, and verification.
- `smilecms.yml`: primary configuration file read via `src.config.Config`.

## Build Pipeline Overview
1. **Workspace prep**: `src.gallery.prepare_workspace` and `src.staging.reset_directory` prepare staging directories, hydrate gallery sidecars, and capture change fingerprints via `src.state.BuildTracker`.
2. **Content ingest**: `src.ingest.load_documents` converts Markdown posts, gallery collections, and music collections into `ContentDocument` models, applying schema validation (`src.validation.validate_document`).
3. **Media planning**: `src.media.pipeline.collect_media_plan` discovers required derivatives and static copies; `src.media.processor.process_media_plan` generates or reuses cached variants under `media/derived/`.
4. **Gallery enrichment**: `src.gallery.pipeline` runs optional ML captioning/tagging (`src.gallery.inference`, `src.gallery.wdtagger`) and merges metadata into collection/image sidecars.
5. **Manifest export**: `src.manifests.ManifestGenerator` and `src.manifests.write_manifest_pages` emit paginated JSON manifests for posts, galleries, and tracks; `src.feeds.generate_feeds` handles RSS/Atom/JSON feed files when enabled.
6. **HTML rendering**: `src.articles.write_article_pages` renders article detail pages using HTML templates in `web/templates/`, wiring media shortcodes to generated derivatives.
7. **Dataset staging**: `src.gallery.export_datasets` and `src.music.export_music_catalog` generate JSONL datasets consumed by the front-end infinite-scroll views.
8. **Static asset staging**: `src.staging.stage_static_site` merges the `web/` bundle into `site/`, prunes stale artifacts, and records staged template paths for incremental builds.
9. **Reporting & verification**: `src.reporting.assemble_report` writes `site/report.json`, while `src.verify.verify_site` scans generated HTML for missing assets; lint and audit commands surface actionable warnings pre-build.

## Core Python Modules
- `src/config.py`: Pydantic models for configuration, derivative profiles, and feature toggles; centralizes path normalization and defaults.
- `src/content/models.py`: `ContentDocument`, `ContentMeta`, `MediaReference`, and `MediaVariant` dataclasses used across ingest, manifests, and rendering.
- `src/gallery/*`: workspace manager, models, metadata cleanup, ML inference, and dataset export for gallery collections; relies on Hugging Face models when `[ml]` extras are installed.
- `src/media/*`: media plan generation, derivative processing via Pillow, asset auditing, and variant attachment back onto documents.
- `src/music/*`: transforms `media/music_collection` folders into datasets and content documents (tracks, lyrics, download directives).
- `src/manifests/*`: manifest data classes and paginated JSON writers to keep front-end payloads small.
- `src/reporting.py` and `src.state.py`: collect build statistics, compute change fingerprints, and persist incremental snapshots in `.cache/build-state.json`.
- `src/validation.py` and `src/verify.py`: schema validation, lint diagnostics, and post-build HTML verification.
- `src/scaffold.py`: provisioning for new posts, galleries, and tracks invoked via `smilecms new`.

## Content & Media Model
- Markdown posts follow a JSON-schema-validated front matter (`src/schemas/content_post.schema.json`) defining slug, status, tags, hero media, and optional download directives.
- Media references are stored relative to logical mounts (`media`, `gallery`, `audio`) defined by `Config.media_mounts`; the pipeline rewrites them to derivative paths during build.
- Gallery collections use `meta.yml` sidecars plus per-image sidecars; they are transformed into `GalleryCollectionEntry`/`GalleryImageEntry` models and published as JSONL datasets.
- Music tracks live in dedicated folders with `meta.yml` metadata and optional `lyrics.md`; datasets and manifests capture duration, download policy, and supporting assets.

## Front-End Bundle
- The static shell in `web/index.html` bootstraps vanilla JS renderers (`web/js/app.js`, `renderer.js`, `journal.js`, `gallery.js`, `music.js`) that hydrate templates using manifest/dataset JSON.
- CSS is split into design tokens (`web/styles/tokens.css`), global primitives (`base.css`, `layout.css`), and feature-specific layers (`components.css`, `gallery.css`, `music.css`).
- HTML `<template>` fragments under `web/templates/` drive reusable UI primitives (tiles, sections, nav, footer).
- Site metadata, navigation, and hero content live in `web/config/site.json`; feeds rely on this file unless overridden in config.
- The front-end assumes streaming JSONL datasets with infinite scroll and progressive enhancement; no heavyweight framework is used.

## Configuration & Deployment
- `smilecms.yml` controls content roots, derivative profiles, gallery/music settings, and output destinations; override paths per environment when needed.
- Optional extras (`pip install -e .[dev]`, `.[ml]`) enable linting/typing and ML enrichment. Missing extras degrade gracefully with warnings.
- `smilecms build` is the primary deployment artifact generator; `smilecms preview` serves `site/` via a threaded HTTP server for review, and `smilecms clean` purges generated assets.
- Generated assets (`site/`, `media/derived/`, `.cache/`) are disposable and should not be checked into version control unless deterministic previews are required.

## Quality & Testing Expectations
- Tests live under `tests/` and use pytest; new features must include unit or integration coverage mirroring expected CLI workflows (e.g., extend `test_cli_*`, `test_gallery_pipeline.py`).
- Run `ruff`, `mypy`, and pytest locally (install via `pip install -e .[dev]`) before raising a PR. Fix type regressions immediately.
- Maintain or update schema fixtures when altering content models (`src/schemas/`, `tests/fixtures/`).
- Use `smilecms lint` to verify content references and schema compliance; treat warnings as blockers unless explicitly waived.

## Coding Standards for Contributions
- **Languages & Tooling**: Python 3.11+ with full type hints; prefer `dataclasses`/`pydantic` models for structured data; front-end additions use ES modules and modern CSS without frameworks.
- **Design Principles**: Preserve deterministic builds, keep pure functions where possible, and isolate side effects behind CLI commands or staging helpers.
- **Error Handling**: Raise typed exceptions (`DocumentValidationError`, `ScaffoldError`, Typer exits) and log actionable warnings through the shared `logging` facilities.
- **Media Processing**: Route all derivatives through `process_media_plan`; do not write directly into `media/derived/` outside of that processor.
- **Configuration**: Never hard-code paths; pull from `Config` objects and respect overrides supplied via `--config`.
- **Docs & Comments**: Update `README.md` and `docs/` when workflow or architecture changes; keep docstrings concise but informative, explaining non-obvious logic.
- **Testing**: Add pytest coverage for new commands, processors, and validation rules. Mock filesystem state with existing fixtures where practical, and assert on tangible outputs (generated paths, report payloads).
- **Front-End**: Keep renderers data-driven; leverage templates, avoid inline HTML string concatenation beyond simple cases, and ensure accessibility (alt text, ARIA attributes) remains intact.
- **Formatting**: Follow `ruff` defaults, use black-compatible formatting, and keep line length <= 100 characters unless there's a strong reason otherwise.

## Automation Notes for AI-Generated Code
- Extend CLI functionality through Typer subcommands in `src/cli.py`; each command should use typed parameters and return `None`, exiting via `typer.Exit` on failure.
- When introducing new build stages, funnel state transitions through `BuildTracker` to keep incremental rebuilds accurate.
- Add new manifest types by extending `src.manifests.models`, updating generator logic, and registering downstream dataset writers and tests.
- For gallery or music enhancements, reuse existing models (`GalleryCollectionEntry`, `MusicExportResult`) to maintain schema stability; update JSONL writers and tests accordingly.
- Every new configuration flag belongs in `src/config.py` with validation, and the default value must keep existing builds backward-compatible.
