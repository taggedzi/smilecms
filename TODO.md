# Todo List

## Authoring Workflow

~~Ship a smilecms new <post|gallery|track> command that scaffolds the recommended front matter and directory layout instead of asking editors to copy templates by hand (docs/content-workflows.md:71, docs/content-workflows.md:124).~~

~~Extend validate_document into a fast smilecms lint/doctor mode that flags missing alt_text, broken hero media, or draft content before a full build, codifying the manual checks described for authors (docs/content-workflows.md:83, build/validation.py:25) and document these features in the project.~~

Turn the existing JSON build report into an HTML/Markdown dashboard so admins can review changes without opening site/report.json manually (build/reporting.py:121).

Add an environment check that confirms optional extras (e.g., .[ml]) are installed and needed models are cached before the pipeline runs, instead of relying on operators to remember those steps (README.md:19).

Add a site crawler to veryify links, file placement, and functionality.

Extract EXIF data from image if availble for display in front end. (or strip exif data if privacy/security wanted)

## Build & CLI Loop

~~Finish the placeholder `preview` and `clean` commands so maintainers can serve `site/` and purge artifacts without dropping to raw `http.server` or manual deletes (build/cli.py:132, build/cli.py:135, README.md:31).~~

~~Introduce change detection/incremental rebuilds to avoid wiping `site/` and `media/derived/` every time, matching the stated requirement while speeding large galleries considerably (build/cli.py:33, docs/requirements.md:46).~~

Add a --watch/--serve loop that rebuilds on file changes while keeping the local preview running, streamlining the repeated smilecms build routine in the docs (README.md:30, docs/content-workflows.md:48).

~~Provide a smilecms media audit (or similar) to surface orphaned/out-of-bounds assets so editors don’t have to police the “assets must live under specific roots” rule manually (docs/content-workflows.md:68).~~

## Front-End Experience

~~Teach the bootstrap script to follow manifest indexes instead of hard-coding content-001.json, so additional manifest chunks load automatically as the library grows (web/js/app.js:3).~~

~~Generate RSS/Atom/JSON feeds directly from the manifests to satisfy the syndication goal and give visitors subscription options (docs/requirements.md:44).~~

Publish a unified search dataset and lightweight global search UI that blends articles, gallery images, and tracks, rather than keeping filtering siloed in each module (web/js/journal.js:107, web/js/music.js:5).

Layer in an offline-friendly service worker or static precache to hit the “offline-friendly baseline” target without leaving static hosting territory (docs/requirements.md:57).
