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
- Galleries belong in `media/image_gallery_raw/<collection-slug>/`. Each folder needs a `meta.yml` describing the collection (`title`, optional `summary`, `tags`, `status`, `published_at`, `hero`). Image files in the folder become gallery assets, and the first image (or the `hero` entry) is used for the tile preview.
- Music tracks live in `media/music_collection/<track-slug>/` with a `meta.yml` that mirrors the gallery structure and additionally supports `audio`, `duration`, and optional asset metadata. The primary audio file is published as-is while artwork/videos in the same folder are exposed as supplementary assets.

## Build & Deploy

1. Install dependencies into your environment (`pip install -e .` or `pip install .`).
2. Run `python -m build build` from the project root. The command regenerates manifests, media derivatives, and stages the web assets.
3. Deploy the contents of the `site/` directory to your hosting provider. That folder now contains everything required to serve SmileCMS (HTML, CSS/JS, templates, manifests, and media derivatives).

For a quick local preview of the production bundle, start a static server inside `site/` (for example, `python -m http.server 8000`) and open `http://localhost:8000/`.
