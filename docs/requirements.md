# Project Requirements — SmileCMS

## 1. Vision & Goals

- Deliver a static-first publishing tool optimized for media-rich personal and small-team sites.
- Centralize all content transformations in a Python build pipeline to keep deployments reproducible and auditable.
- Serve visitors via static HTML/JS/CSS with JSON-fed rendering, enabling cheap hosting and easy caching.
- Provide a reusable toolkit (templates + CLI) so others can launch similar sites with minimal setup.

## 2. Personas & Workflows

- **Primary editor**: single-site owner who edits text/media locally, then triggers a rebuild and publish.
- **Future collaborator**: occasional contributor who can follow documented steps to add content or tweak templates.
- **Visitor**: consumes read-only content with fast load times even on slow devices or connections.

High-level workflow:

1. Author updates source content (markdown, metadata files, media).
2. Run the Python build command to regenerate manifests, derivatives, and static site assets.
3. Inspect build artifacts locally (preview server/watch mode).
4. Deploy generated assets to a static host/CDN.

## 3. Content Model

- Text posts (articles, notes, announcements) with optional tags, publish date, hero media, and related links.
- Media galleries with large image sets (15–20k assets) and optional albums/collections.
- Audio/video tracks with metadata (duration, codecs, captions).
- Global site metadata: navigation, contact info, SEO/OpenGraph fields.

Source formats:

- Markdown or MDX for prose content, coupled with front-matter YAML.
- JSON/YAML descriptors for collections and global config.
- Raw media files organized under dedicated roots:
  - `/content/media/` for article assets
  - `/media/image_gallery_raw/` for gallery collections and sidecars
  - `/media/music_collection/` for audio tracks and artwork

## 4. Build Pipeline Requirements (Python)

- Parse source directories, validate against schemas, and produce canonical JSON manifests per content type.
- Generate media derivatives (thumbnails, resized images, audio waveforms) and register them in manifests.
- Split large manifests into paginated or chunked JSON files to keep client payloads small.
- Produce search indexes (optional) and feed files (RSS/Atom/JSON Feed).
- Offer an on-demand verification pass that checks generated HTML for broken internal links or missing assets before deployment.
- Emit diagnostic logs and a report summarizing new/changed content, build duration, and warnings.
- Support incremental builds to rebuild only altered content where feasible (reuse cached derivatives and prune stale artifacts instead of wiping outputs).
- Provide unit/integration tests for content parsing and manifest generation.

## 5. Front-End Architecture (Static HTML/JS)

- Base HTML shell rendered at build time (lightweight templating or static file).
- Client-side renderer (vanilla JS or minimal framework) that:
  - Loads bootstrap JSON (site config, navigation).
  - Fetches paginated manifests on demand (lazy loading, infinite scroll, search filters).
  - Renders media galleries with responsive layouts and progressive image loading.
- Accessibility considerations: semantic HTML, keyboard navigation, ARIA roles, captions/alt text surfaced from metadata.
- Offline-friendly baseline (service worker optional, but design should allow future enhancement).

## 6. Deployment & Operations

- Single command (`smilecms build`) produces all artifacts under `/site/`.
- Optional `smilecms preview` launches a local static server with live reload.
- Deployment script/docs for pushing `/site/` to static hosts (S3/CloudFront, Netlify, GitHub Pages, etc.).
- Cache-busting strategy (content-hashed asset filenames, manifest versioning).
- Backups/versioning: instructions for storing raw content and generated artifacts in git or object storage.

## 7. Non-Functional Requirements

- **Performance**: initial page payload < 250 KB; manifest chunks ≤ 500 KB; first meaningful paint < 2 s on mid-range mobile.
- **Scalability**: handle 20k+ media items without exhausting client memory; build pipeline must process large sets within acceptable time (target < 10 min full rebuild).
- **Portability**: run on Python 3.11+, no external services required; optional integrations behind feature flags.
- **Maintainability**: clear module boundaries, typed Python code (type hints + mypy), automated lint/format.
- **Security**: generated site is static; ensure pipeline sanitizes filenames/paths to prevent injection when deployed.

## 8. Extensibility & Packaging

- Expose configuration file (`smilecms.yml`) controlling content paths, build options, and theme selection.
- Provide plugin hooks for custom content processors or output adapters.
- Include starter themes/templates and example content for new users.
- Document how to add new content types (schema extension, templates, front-end renderers).

## 9. Documentation Plan

- `README.md`: quickstart, build/deploy commands.
- `docs/requirements.md`: this document.
- `docs/architecture.md`: future technical deep dive (pipeline diagrams, module overview).
- `docs/contributing.md`: coding guidelines, testing, release process.
- `docs/usage/`: tutorials for adding content, managing media, customizing themes.
