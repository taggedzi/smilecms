# SmileCMS CLI Usage

This guide collects the practical command-line workflows that drive the SmileCMS build system. It explains the build pipeline, documents every CLI command and option, and provides example invocations with the expected side effects. Keep it alongside `docs/content-workflows.md` when you are iterating on content or automating deployments.

## Getting Started
- Activate a Python 3.11+ environment and install the project: `pip install -e .` (add extras like `.[dev]` or `.[ml]` when those features are needed).
- Run all commands from the project root so the CLI can locate `smilecms.yml` and the content/media directories.
- The CLI uses [Typer](https://typer.tiangolo.com/), so global help is always available via `smilecms --help` and `smilecms <command> --help`.

## Build Pipeline Overview

A successful `smilecms build` run executes the following stages:
- **State detection** – `BuildTracker` hashes key inputs and reports whether this is the first build, an incremental rebuild, or a no-change reuse. Pass `--force` to clear cached outputs before the pipeline starts.
- **Workspace prep** – ensures the configured `site/` and media derivative directories exist (or are reset when forcing), and primes the gallery workspace.
- **Content ingest** – loads Markdown, YAML, and sidecar metadata into structured documents; validation errors stop the run early.
- **Media processing** – copies or renders the configured derivative profiles, attaches the generated variants to content documents, and refreshes gallery derivative mappings.
- **Artifact generation** – writes manifests under `site/manifests/`, generates syndication feeds, exports gallery datasets, writes per-article pages, and stages static assets from `web/` into the site bundle.
- **Reporting** – emits `site/report.json`, prints summary statistics, and aggregates warnings from media, gallery, and music subsystems.
- **Persistence** – saves the computed fingerprints and tracked template paths so subsequent runs can skip untouched work.

The preview and verification commands operate on the generated bundle in `site/`, so run `smilecms build` (or `smilecms build --force`) before invoking them.

## Command Reference

### Common Options
- `--config PATH`, `-c PATH`: every command defaults to `smilecms.yml`. Use this option to target an alternate configuration file.
- Boolean flags follow Typer conventions: `--flag / --no-flag` for toggles (e.g., `--open-browser/--no-open-browser`) and plain `--force`, `--strict`, `--cache`, `--json` for simple on/off switches.

### `smilecms build`
- **Purpose:** Perform an incremental or full rebuild of the static site bundle.
- **Options:**
  - `--config PATH`: choose a different config file.
  - `--force`, `-f`: delete the output directories (`site/`, media derivatives) before rebuilding.
- **Inputs:** `smilecms.yml` (or the path passed via `--config`), source Markdown in `content/`, gallery collections under `media/image_gallery_raw/`, music collections under `media/music_collection/`, and templates in `web/`.
- **Outputs:** refreshed `site/` bundle (HTML, CSS/JS, manifests), `media/derived/` assets, gallery datasets under `site/data/`, music exports, and a build report (`site/report.json`). The console prints a structured summary highlighting counts, locations, and any warnings gathered during the run.
- **Example:**
  ```bash
  smilecms build
  # -> prints incremental/force status, document and media statistics,
  #    lists staged assets, and writes site/report.json
  ```

### `smilecms new`
- **Purpose:** Scaffold content skeletons for posts, galleries, or music tracks using the project conventions.
- **Positional arguments:**
  - `kind`: one of `post`, `gallery`, or `track`.
  - `slug`: identifier used for filenames/directories; it is normalized automatically.
- **Options:**
  - `--title TEXT`, `-t TEXT`: override the title derived from the slug.
  - `--config PATH`: load alternate defaults (e.g., custom content roots).
  - `--force`, `-f`: allow overwriting existing scaffold files.
- **Outputs:** the command prints a summary of created and updated files. Depending on the `kind`, it writes the following:

  | Kind    | Files/Folders created                            | Notes |
  | ------- | ------------------------------------------------ | ----- |
  | `post`  | `content/posts/<slug>.md`, `content/media/<slug>/` | Markdown stub with YAML front matter plus a media directory seeded with `.gitkeep`. |
  | `gallery` | `media/image_gallery_raw/<slug>/meta.yml`, collection directory | Metadata stub and directory ready for raw images. |
  | `track` | `media/music_collection/<slug>/meta.yml`, `lyrics.md` | Metadata scaffold plus lyrics placeholder alongside the track folder. |

- **Example:**
  ```bash
  smilecms new post my-first-post --title "My First Post"
  # -> reports normalized slug (if changed) and lists each scaffolded file
  ```

### `smilecms lint`
- **Purpose:** Run fast content validation to surface missing metadata, unresolved media, or other authoring issues without generating the full site.
- **Options:**
  - `--config PATH`
  - `--strict`: treat warnings as errors (exit code 1 when warnings are present).
- **Outputs:** Prints each issue grouped by severity (`ERROR` or `WARNING`), including the source path and pointer (front-matter or field). The summary line reports totals, and the exit status is 0 for a clean run (or warning-only run when `--strict` is not set).
- **Example:**
  ```bash
  smilecms lint --strict
  # -> exits with 1 if any warnings or errors remain
  ```

### `smilecms audit media`
- **Purpose:** Inspect media references across posts, galleries, and music content to detect missing or misplaced assets.
- **Options:**
  - `--config PATH`
  - `--json`: emit machine-readable JSON instead of rich console output.
- **Outputs:** The human-readable mode prints counts for total assets and references, then lists out-of-bounds references, missing assets, orphan files, and stray files. The JSON output mirrors that structure with `summary`, `missing_references`, `out_of_bounds_references`, `orphan_assets`, and `stray_assets` keys.
- **Example:**
  ```bash
  smilecms audit media --json > media-audit.json
  # -> returns exit code 0 and writes an audit payload suitable for tooling
  ```

### `smilecms verify`
- **Purpose:** Crawl the generated `site/` bundle to find missing links, unresolved assets, or other integrity issues before deployment.
- **Options:**
  - `--config PATH`
  - `--report PATH`, `-r PATH`: optionally write a plaintext report summarizing findings.
- **Outputs:** The command prints the scan target, reports any issues by severity, and exits with code 1 if errors are present. When `--report` is supplied, it writes a UTF-8 text file with the same content.
- **Example:**
  ```bash
  smilecms verify --report verify-report.txt
  # -> scans site/, prints warnings/errors, and writes verify-report.txt
  ```

### `smilecms preview`
- **Purpose:** Serve the generated `site/` directory over HTTP for local review.
- **Options:**
  - `--config PATH`
  - `--host TEXT`: interface to bind (default `127.0.0.1`).
  - `--port INT`, `-p INT`: TCP port (default `8000`).
  - `--open-browser/--no-open-browser`: automatically launch a browser tab after the server starts (default is `--no-open-browser`).
- **Outputs:** Starts a threaded HTTP server rooted at `site/`, printing the bound URL and advising when the directory is empty or missing. The process runs until interrupted (Ctrl+C). Exit code is 0 on a clean shutdown, 1 when binding fails.
- **Example:**
  ```bash
  smilecms preview --port 9000 --open-browser
  # -> hosts the site bundle at http://127.0.0.1:9000/
  ```

### `smilecms clean`
- **Purpose:** Remove build artifacts so the next `smilecms build` starts from a blank slate.
- **Options:**
  - `--config PATH`
  - `--cache`: also remove the configured cache directory (defaults to `.cache/` in `smilecms.yml`).
- **Outputs:** For each target (site output, media derivatives, optional cache) the command prints whether it removed or skipped the directory, then reports how many paths were deleted. This command is idempotent—missing directories are simply noted and skipped.
- **Example:**
  ```bash
  smilecms clean --cache
  # -> removes site/, media/derived/, and .cache/ when they exist
  ```

## Tips for Automation
- Chain `smilecms lint --strict`, `smilecms build`, and `smilecms verify` in continuous integration to fail early on content or asset regressions.
- Use `smilecms audit media --json` to feed dashboards or pre-commit hooks that enforce media hygiene.
- When scripting, rely on exit codes: non-zero statuses signal actionable failures (validation errors, missing outputs, or verification issues).

