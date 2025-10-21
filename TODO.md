# Implementation Script

- [x] Gather context: audit src/articles.py, existing template files under templates/, JSON outputs, and how articles/galleries/music data is produced; capture current render pipeline for reference.
- [x] Add dependency: update project packaging (e.g., pyproject.toml or requirements.txt) to include Jinja2>=3.x; adjust build tooling or virtualenv bootstrap as needed.
- [x] Introduce theme layout: scaffold a default theme directory (templates/ or themes/default/) with base.html, partials/header.html, partials/nav.html, partials/footer.html, pages/article.html, pages/index.html, etc., using Jinja2 block syntax and placeholders matching the planned data context.
- [x] Refactor renderer: replace string-built HTML in ArticleBodyRenderer, SiteChromeRenderer, ArticleMainRenderer, and TemplateComposer with Jinja2 rendering calls. Build context dictionaries (site chrome, article metadata, asset URLs, JSON endpoints) and render the appropriate template; keep JSON generation and writing logic intact.
- [x] Implement loader + theme manifest: add a loader that resolves templates from the active theme (filesystem loader with inheritance), validate required templates exist, and support fallbacks if missing. Consider a theme.json describing available pages/assets.
- [x] Adjust inline script handling: move the JS snippet into a template partial or static asset referenced from templates instead of injecting via Python.
- [x] Ensure static JSON feeds remain referenced from templates/JS so client-side hydration still works; expose needed URLs in the context passed to templates.
- [x] Update build flow: wire the new renderer into ArticlePageWriter so final HTML still lands in output/posts/<slug>/index.html; remove now-unused HTML assembly helpers.
- [ ] Run formatting/tests: execute lint/unit/static site build commands (pytest, python -m src.cli build, etc.) to confirm no regressions and newly generated HTML looks correct.
- [x] Document theme API: add or update docs/theme-dev.md detailing context variables, required template files, asset expectations, and the dev workflow for front-end contributors.
- [x] Add regression coverage: create snapshot/golden tests or fixture-based checks ensuring templates render expected HTML for representative content (article with media, missing hero, etc.).

# Gallery & Music Jinja Migration

- [x] Audit existing gallery and music static pages plus front-end scripts to understand data dependencies and required markup.
- [x] Extract reusable template asset/context helpers so gallery and music pages can share the Jinja environment.
- [x] Extend the default theme manifest and templates to add gallery and music entrypoints, including page-specific layouts, styles, and scripts.
- [x] Implement Python renderers that generate `gallery/index.html` and `music/index.html` via Jinja, wiring them into the build pipeline.
- [x] Update gallery and music client scripts to consume the new data attributes / shared context emitted by the templates.
- [x] Ensure the build step writes the new pages without stale static copies and update staging summaries accordingly.
- [x] Add unit tests covering rendered gallery and music pages (titles, data attributes, assets, navigation state).
- [ ] Refresh documentation or developer notes if the theming API gains new context fields and rerun formatting/tests to validate the changes.
