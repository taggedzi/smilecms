# Smile CMS

## Project Summary

The goal of the project is to create a VERY simple to maintain CMS website for single admin or small groups to maintain. Using as little server configuration as possible, trying to serve it up as a static website, where all the data is generated off site, and built by a basic HTML/CSS/JS template system that pulls the content from the static content provided (ie jsonl, json, static media, etc).  

Allowing support for:

* Basic static text display (static MD/HTML files) for individual pages like About, or Contact, FAQ, etc. Things that are part of the site that probably will not be updated frequently.
* Blog/Artilce/Post like content (static MD files with image support) allowing continually updated/searchable/taggable content.
* Image Gallery (jpg, png, webp, gif, svg support) allowing the display of catagorized (grouped) gallery images with a title and caption and the ability to pull out and display (light box) individual images, as well as all meta data available title, resolution, tags, caption, etc. Allow infinite scroll on the gallery page.
* Music Catalog (mp3, wave, mp4) allowing the display of the cover art, title, and description information AND the ability to play the audio or video(optional) if available with also the ability to display all relevant metadata for the sounds/songs. Allow infinite scroll on the catalog page.

## Requirements


## Content Layout

- Articles live under `content/` as Markdown. Assets referenced by articles should be stored in `content/media/` and referenced with paths like `media/hero-image.jpg`; the build will resolve them and emit derivatives under `site/media/derived/media/...`.
- Inside article bodies you can embed local assets with shortcodes: `[Caption](img:media/example.jpg)`, `[Track Title](audio:audio/example.mp3)`, or `[Clip Title](video:media/example.mp4)`. These resolve to the processed assets in the static bundle.
- The journal archive lives at `/journal/` in the generated site. It loads the latest manifest so new posts appear automatically and supports search / sort without additional configuration.
- Galleries belong in `media/image_gallery_raw/<collection-slug>/`. Each folder keeps a `collection.json` describing the collection (`title`, optional `summary`, `tags`, `sort_order`, `cover_image_id`). Image files sit alongside machine-maintained sidecars (`<image>.json`) that capture generated metadata, ML tags, and per-run LLM clean-ups. The build orchestrator refreshes these sidecars automatically, emits media derivatives, and writes searchable datasets to `site/data/gallery/`. The shipped front-end at `/gallery/` streams those JSONL files to render the infinite-scroll experience.
- Music tracks live in `media/music_collection/<track-slug>/` with a `meta.yml` that mirrors the gallery structure and additionally supports `audio`, `duration`, and optional asset metadata. The primary audio file is published as-is while artwork/videos in the same folder are exposed as supplementary assets.

## Build & Deploy

1. Install dependencies into your environment (`pip install -e .` or `pip install .`).
2. Run `python -m build build` from the project root. The command regenerates manifests, media derivatives, and stages the web assets.
3. Deploy the contents of the `site/` directory to your hosting provider. That folder now contains everything required to serve SmileCMS (HTML, CSS/JS, templates, manifests, and media derivatives).

For a quick local preview of the production bundle, start a static server inside `site/` (for example, `python -m http.server 8000`) and open `http://localhost:8000/`.
