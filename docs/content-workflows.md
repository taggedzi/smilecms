# Content & Build Workflows

This guide collects the practical steps needed to work on SmileCMS after the initial setup. It focuses on the two active content types: **journal entries** (Markdown posts that can embed media) and **image galleries** (collection-driven photo sets with generated metadata). Keep it close while iterating on the project or handing it off.

---

## 1. Prerequisites

- Python **3.11+**
- [Pillow](https://python-pillow.org/) and other runtime dependencies are installed automatically when you install the project (see below).
- For automatic gallery captioning/tagging you also need the optional ML extras (`pip install -e .[ml]`) and a machine that can run Hugging Face transformer models (CPU works, GPU is faster). If the extras are missing, the pipeline simply skips ML enrichment and logs a warning.

```bash
python -m venv .venv
.venv\Scripts\activate    # or `source .venv/bin/activate` on macOS/Linux
pip install -e .          # add `.[dev]` for lint/test tooling, `.[ml]` for gallery tagging
```

Project configuration lives in `smilecms.yml`. Key directories referenced throughout this doc:

| Purpose                      | Path (default)                         |
| ---------------------------- | -------------------------------------- |
| Markdown posts               | `content/posts/`                       |
| Post-local media             | `content/media/`                       |
| Raw gallery collections      | `media/image_gallery_raw/<slug>/`      |
| Derived media output         | `media/derived/`                       |
| Final static site bundle     | `site/`                                |
| Gallery datasets for the web | `site/data/gallery/`                   |

---

## 2. Build & Preview Loop

The CLI entry point is exposed as `smilecms` (via `pyproject.toml`). Running a build performs the complete pipeline in this order:

1. **Workspace preparation** – resets `site/` and the derivative media directory, scans gallery collections, and ensures sidecar metadata files exist.
2. **Content ingest** – parses Markdown posts into structured `ContentDocument` objects, validates required front matter, and collects referenced media.
3. **Media processing** – copies or resizes media into `media/derived/` following the profiles configured in `smilecms.yml`. Image derivatives (`thumb`, `large`) are generated with Pillow; non-image assets are copied as-is.
4. **Gallery enrichment** – updates collection and image sidecars with generated captions/tags (when ML extras are available), cleans metadata with the lightweight LLM helper, and attaches derivative paths back onto each image record.
5. **Manifest and article output** – writes paginated JSON manifests under `site/manifests/` and renders individual article pages to `site/posts/<slug>/index.html` using the HTML templates packaged in `web/`.
6. **Gallery datasets** – emits `collections.json`, per-collection `*.jsonl`, and a global `images.jsonl` under `site/data/gallery/` for the front-end gallery experience.
7. **Report & logs** – saves a build report (`site/report.json`) and prints stats to the console, including any warnings about missing media or gallery issues.
8. **Static assets staging** – copies the `web/` directory into `site/` so CSS, JS, and templates ship with the bundle.

Command examples:

```bash
smilecms build            # full rebuild using smilecms.yml
smilecms build --config custom.yml  # point to an alternate config file
```

Run `smilecms lint` to catch missing alt text, unpublished drafts, or broken hero media before kicking off a full build. Add `--strict` when you want warnings to fail the command (handy for CI or pre-commit hooks).

Preview the generated site by serving the `site/` directory:

```bash
python -m http.server 8000 --directory site
# Visit http://localhost:8000/
```

> `smilecms preview` and `smilecms clean` are stubs today. Use the commands above for now.

---

## 3. Scaffolding New Content

Editors can bootstrap new entries without copying templates by hand. Run `smilecms new <post|gallery|track> <slug> [--title "Display Title"]` from the project root while your virtual environment is active.

What the command expects:

- A slug (letters/numbers/hyphens) that will be used for filenames and directories. It is normalized automatically (e.g. `My First Post` → `my-first-post`).
- An optional title override. If omitted, the command derives a readable title from the slug.
- By default, the command refuses to overwrite existing files; pass `--force` to regenerate scaffolds after double-checking that it is safe to do so.

What the command provides (per content type):

- **Posts** – creates `content/posts/<slug>.md` with the recommended front matter and body stub, plus `content/media/<slug>/` containing a `.gitkeep` placeholder so asset uploads have a dedicated folder. The front matter matches the template guidelines below, including `hero_media` and `assets` sections ready for editing.
- **Galleries** – creates `media/image_gallery_raw/<slug>/meta.yml` (JSON formatted for compatibility with the pipeline) and drops a `.gitkeep` in the collection directory. The metadata includes timestamps, empty tags, and placeholders for hero/cover images. Editors then copy raw images into the same directory; sidecars are generated on the next build.
- **Tracks** – creates `media/music_collection/<slug>/meta.yml` populated with the required fields (`audio`, `download`, `status`, etc.) and a `lyrics.md` stub. Editors add the audio file and supporting artwork to the same folder, then update metadata/lyrics as needed.

After scaffolding:

1. Add or replace media files as instructed by the notes printed in the CLI output.
2. Update titles, summaries, tags, and descriptions in the generated metadata/front matter.
3. Run `smilecms build` to ingest the new content; inspect the CLI summary for warnings about missing assets or metadata.

The sections that follow dive into authoring expectations for each content type—the scaffolds emitted by `smilecms new` align with these requirements, so you can treat them as starting points rather than finished drafts.

---

## 3. Journal Entries (Markdown + Media)

### File layout

- Each entry lives in `content/posts/<slug>.md` with YAML front matter.
- Shared images/audio/video that belong to the article **must** go in `content/media/`. They are referenced with relative paths such as `media/my-image.jpg`. Paths outside this directory will be rejected during the build.
- The build pipeline generates derivatives and stores them under `media/derived/` (no manual copying required).
- Run `smilecms audit media` to list missing references, orphaned uploads, or assets sitting outside the approved roots before committing.

### Front matter template

```yaml
---
title: "My Post Title"
slug: my-post-title          # autogenerated from filename when omitted
status: published            # draft | published | archived
published_at: 2025-10-10T16:00:00Z
updated_at: 2025-10-11T14:20:00Z  # optional
tags: [art, update]
hero_media:
  path: "media/hero-image.jpg"
  alt_text: "Describe the hero image for accessibility"
assets:
  - path: "media/inline-still.jpg"
    alt_text: "Caption text"
  - path: "audio/song-title/song-title.mp3"
    title: "Song Title"
---
Markdown body starts here…
```

Run `smilecms new post <slug> --title "Display Title"` to scaffold this front matter and a companion `content/media/<slug>/` asset folder.

Notes:

- `status` must be `published` for the post to appear on the site and in manifests.
- All timestamps are stored in ISO-8601; the parser will normalize naive values to UTC.
- `assets` is optional but helps the pipeline pre-register media before it scans the body.
- Derivative variants are attached automatically so the front-end can pick the right size.

### Embedding media in Markdown

Use the shortcode syntax already wired into `build/articles.py`:

- `[Caption](img:media/example.jpg)` – renders an `<img>` with caption and figure wrapper.
- `[Label](audio:audio/song.mp3)` – renders an `<audio>` element with controls.
- `[Label](video:media/clip.mp4)` – renders an HTML5 `<video>` player.

During the build these references resolve to the generated assets in `/media/derived/...`. If an asset cannot be found you’ll see a warning and the page will render a “Missing media” notice instead.

### Output

- Individual article pages: `site/posts/<slug>/index.html`
- Manifests used by the home page/journal index: `site/manifests/content-page-*.json`
- Media derivatives: `media/derived/{thumb,large}/...`

---

## 4. Gallery Collections

### Source structure

```
media/image_gallery_raw/<collection-slug>/
├── meta.yml             # collection sidecar (auto-generated if missing)
├── image-1.jpg
├── image-1.json         # image sidecar maintained by the pipeline
├── image-2.jpg
└── …
```

Run `smilecms new gallery <slug> --title "Display Title"` to bootstrap the folder and collection metadata before dropping in raw images.

- Raw images sit next to their `.json` sidecars. When the pipeline discovers a new file it will create a sidecar with baseline metadata (title from stem, timestamps, etc.).
- `meta.yml` can be JSON or YAML and accepts the fields defined in `build/gallery/models.py` (`title`, `summary`, `tags`, `sort_order`, etc.). Missing fields are auto-filled.
- Drop new images into the collection folder and rerun `smilecms build`; derivatives and metadata refresh automatically. Assets placed outside `media/image_gallery_raw/` will not be picked up.

**Tip:** Give each asset a unique filename (stem). If you drop both `painting.png` and `painting.jpg` into a collection, the single sidecar (`painting.json`) can only reference one of them. The other file will be reported as an orphan during `smilecms audit media`. Remove the unwanted duplicate (or create a second image/sidecar pair) and update the remaining sidecar to resolve the warning.

### Optional ML enrichment

- Install the `[ml]` extra (`pip install -e .[ml]`) to enable automatic captioning and tagging via Hugging Face models. Without it the rest of the pipeline still runs, but `tags`/`captions` stay untouched unless manually edited.
- Model downloads are cached under `~/.cache/huggingface/`. The first run may take several minutes.
- Toggle ML behavior in `smilecms.yml` (`gallery.llm_enabled`, `gallery.tagging_enabled`). Any warnings are surfaced after the build.

### What the build produces

- Derivative images in `media/derived/{thumb,large}/gallery/<collection>/<file>` following the profiles defined in `smilecms.yml` (`gallery.profile_map` maps semantic roles to derivative profiles).
- `site/data/gallery/collections.json` – summary plus list of collections used by `web/js/gallery.js`.
- `site/data/gallery/<collection>.jsonl` – line-delimited records for the collection view (the front-end streams these for infinite scroll).
- `site/data/gallery/images.jsonl` – global index combining all collections (used for search/autocomplete).
- Updated sidecars back in `media/image_gallery_raw/...` reflecting derivatives, captions, tags, and quality checks.

### Publishing workflow

1. Place new raw images inside the collection folder (or create a new folder for a new collection).
2. Optionally edit `meta.yml` to provide human-friendly titles/descriptions or to lock fields before the pipeline runs.
3. Run `smilecms build`. Watch the console output for warnings about missing media or tagging failures.
4. Review the generated gallery at `site/gallery/index.html` (via a local static server).

---

## 5. Music Tracks

- Store each track inside `media/music_collection/<slug>/` with its metadata file (default `meta.yml`).
- The build treats that folder as the sole source for audio and related artwork; references outside the directory will be marked missing during planning.
- Audio assets are copied into `media/derived/audio/...` so the music catalog and download links work without additional setup.

Run `smilecms new track <slug> --title "Display Title"` to scaffold the track directory, metadata file, and placeholder lyrics document before adding audio and artwork.

Example `meta.yml`:

```yaml
title: "Melting Away [House Mix]"
summary: "A house song about melting away with God."
description: |
  Long-form description (Markdown allowed) that powers the modal view.
tags: [Progressive House, Cinematic EDM, Uplifting]
status: published
published_at: 2025-08-30T19:18:00Z
duration: 270           # seconds
audio: melting-away.mp3 # primary audio file (required)
download: true          # or `download: alt-master.wav` for a custom file
audio_meta:
  mime_type: audio/mpeg
assets:
  cover.png:
    alt_text: "Waterfall in a desert."
  visualizer.mp4:
    title: "Visualizer"
```

- `download` accepts `true` (use the primary audio), a specific filename, or an object `{ enabled: true, path: "alt.wav" }`. The referenced file must live beside `meta.yml`.
- Optional `download_meta` can provide alt/title data for the download asset.
- Drop an optional `lyrics.md` in the same folder to surface song lyrics in the music modal; if the file is missing the catalog simply shows the description (ideal for instrumentals).
- All images/videos in the folder automatically become supporting media; the first image is used as cover art on the catalog page.
- After running `smilecms build`, the catalog lives at `/music/` with searchable, infinite-scroll tiles and deep links (`/music/?track=<slug>`). Copy any track URL to share the exact modal view.
- The build exports datasets to `site/data/music/manifest.json` and `site/data/music/tracks.jsonl`, which power the front-end catalog.

---

## 6. Deployment Checklist

- Ensure the latest build completed without blocking errors (`smilecms build` exit code 0).
- Inspect `site/report.json` or the console summary for warnings (missing media, gallery errors).
- Deploy the entire `site/` directory to your static host (S3 + CloudFront, Netlify, GitHub Pages, etc.). The bundle contains HTML, CSS/JS, JSON manifests, and media derivatives.
- Keep the source directories (`content/`, `media/`, `smilecms.yml`) under version control so builds are reproducible. The derived `media/derived/` folder can be regenerated and usually doesn’t need to be committed unless you want deterministic previews without rebuilding.

---

## 7. Further Reading

- [`README.md`](../README.md) – quickstart and high-level overview.
- [`docs/frontend.md`](frontend.md) – layout and styling notes for the web front end.
- [`build/`](../build/) package – Python source for the pipeline if you need to extend or debug the process.

If you keep this workflow document in sync with code changes, future contributors (or your future self) can confidently pick up development, extend content types, or adjust the build pipeline without relearning the project from scratch.
