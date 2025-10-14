# Smile CMS

## Project Summary

The goal of the project is to create a VERY simple to maintain CMS website for single admin or small groups to maintain. Using as little server configuration as possible, trying to serve it up as a static website, where all the data is generated off site, and built by a basic HTML/CSS/JS template system that pulls the content from the static content provided (ie jsonl, json, static media, etc).  

Allowing support for:

* Basic static text display (static MD/HTML files) for individual pages like About, or Contact, FAQ, etc. Things that are part of the site that probably will not be updated frequently.
* Blog/Artilce/Post like content (static MD files with image support) allowing continually updated/searchable/taggable content.
* Image Gallery (jpg, png, webp, gif, svg support) allowing the display of catagorized (grouped) gallery images with a title and caption and the ability to pull out and display (light box) individual images, as well as all meta data available title, resolution, tags, caption, etc. Allow infinite scroll on the gallery page.
* Music Catalog (mp3, wave, mp4) allowing the display of the cover art, title, and description information AND the ability to play the audio or video(optional) if available with also the ability to display all relevant metadata for the sounds/songs. Allow infinite scroll on the catalog page.

## Requirements

- Python **3.11+**
- Recommended tools (installed via extras):
  - `pip install -e .[dev]` for formatting (`ruff`), typing (`mypy`), and testing (`pytest`).
  - `pip install -e .[ml]` to enable automatic gallery captioning/tagging (CPU-compatible Hugging Face models).
- Optional external binaries:
  - Image processing relies on Pillow only; ffmpeg is *not* required today.

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate  # or `source .venv/bin/activate`
pip install -e .        # add extras like `.[dev]` or `.[ml]` when needed

smilecms build          # full rebuild using smilecms.yml
python -m http.server 8000 --directory site  # preview at http://localhost:8000/
```

The `smilecms build` command resets the output directories, generates media derivatives, writes manifests, renders article pages, exports gallery datasets, and stages the static `web/` assets into `site/`.

## Content Layout & Workflows

All source content stays in the repository so the build is deterministic:

| Type                | Source directory                               | Output |
| ------------------- | ---------------------------------------------- | ------ |
| Journal posts       | `content/posts/*.md`                           | `site/posts/<slug>/index.html` |
| Post media          | `content/media/` *(required)*                  | `media/derived/...` (generated) |
| Galleries           | `media/image_gallery_raw/<collection>/` *(required)* | `site/data/gallery/*.json[l]` + `media/derived/gallery/...` |
| Music catalog       | `media/music_collection/<track>/` *(required)* | `site/data/...` (future audio manifests) + `media/derived/...` |
| Static front-end    | `web/`                                         | Copied into `site/` during build |

- **Journal entries** use Markdown with YAML front matter. All referenced media must live under `content/media/`; shortcodes like `[Caption](img:media/example.jpg)` embed those assets and are resolved to generated derivatives (`/media/derived/...`) during the build.
- **Galleries** keep raw images and sidecar metadata together under `media/image_gallery_raw/…`. The build pipeline enriches sidecars, generates derivative sizes (`thumb`, `large` by default), and publishes JSON/JSONL datasets that power `/gallery/`.
- **Music catalog** follows the same conventions under `media/music_collection/` (metadata + media). Assets outside that hierarchy are rejected so each track remains self-contained; optionally add a `lyrics.md` file beside `meta.yml` to surface song lyrics inside the catalog modal.

See [`docs/content-workflows.md`](docs/content-workflows.md) for step-by-step instructions covering authoring, media handling, ML enrichment, and deployment.

## Build & Deploy

1. Install the project (see **Quick Start**).
2. Run `smilecms build` (or `python -m build.cli build`) from the project root. Configuration defaults come from `smilecms.yml`.
3. Inspect the console summary or `site/report.json` for warnings (missing media, gallery tagging failures).
4. Deploy the entire `site/` directory to your static host/CDN. It already contains HTML, CSS/JS, JSON manifests, and media derivatives.

For a quick local preview of the production bundle, start a static server inside `site/` and visit `http://localhost:8000/`.

## Additional Documentation

- [`docs/content-workflows.md`](docs/content-workflows.md) — authoring pipeline, build loop, and deployment checklists for journal entries and galleries.
- [`docs/frontend.md`](docs/frontend.md) — layout, design, and front-end module overview.
- [`docs/requirements.md`](docs/requirements.md) — product requirements and technical goals.

Keep the docs in sync with pipeline changes so future contributors can pick up the project without guesswork.
