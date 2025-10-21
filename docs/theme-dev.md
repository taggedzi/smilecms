# Theme Development Guide

SmileCMS now ships with a Jinja2-based theming system designed to separate presentation from the Python build pipeline. This document explains the default theme structure, how templates are loaded, and which context objects are available when rendering pages.

## Directory Layout

Themes live under `web/themes/<theme-name>/`. The default theme is located at `web/themes/default/` and contains:

- `theme.json` – manifest describing entrypoints, partials, assets, and default options.
- `base.html` – root layout providing the app shell, global assets, and shared partial inclusions.
- `pages/` – page-level templates (e.g., `article.html`, `index.html`) that extend `base.html`.
- `partials/` – reusable fragments such as `header.html`, `nav.html`, `footer.html`, and `inline-script.html`.

When the build runs, the theme directory is resolved from `Config.themes_root`. By default this is `<templates_dir>/themes`. Set `Config.theme_name` to switch the active theme. If the requested theme is missing or incomplete, SmileCMS automatically falls back to the bundled `default` theme.

## Manifest Schema

`theme.json` follows the structure read by `src.themes.ThemeManifest`:

```json
{
  "name": "SmileCMS Default Theme",
  "version": "0.1.0",
  "entrypoints": {
    "base": "base.html",
    "article": "pages/article.html",
    "index": "pages/index.html",
    "gallery": "pages/gallery.html",
    "music": "pages/music.html"
  },
  "partials": {
    "header": "partials/header.html",
    "nav": "partials/nav.html",
    "footer": "partials/footer.html",
    "inline_script": "partials/inline-script.html"
  },
  "assets": {
    "styles": [...],
    "scripts": [...]
  },
  "default_shell_theme": "dark"
}
```

- **entrypoints** map named pages (e.g., `article`, `gallery`) to template files. `base` is required.
- **partials** are optional helpers included by `base.html`. Missing partials simply aren’t rendered.
- **assets.styles** is an ordered list of stylesheet URLs.
- **assets.scripts** contains objects with `src`, and optional `type`, `defer`, `async`, `integrity`, `crossorigin`.
- **default_shell_theme** is applied when no explicit theme is set on the rendered page.

If a custom theme omits styles or scripts, the loader reuses values from the fallback theme.

## Template Context

All page entrypoints inherit a shared context surface; individual pages (e.g., `article`, `gallery`, `music`) add their own blocks under the keys noted below.

| Key | Description |
| --- | --- |
| `site` | `{ "title": str, "tagline": str }` calculated from `web/config/site.json`. |
| `navigation` | `{ "items": [{"label", "href", "active"}], "menu_open": bool }`. |
| `footer` | `{ "copy": str, "links": [{"label", "href", "external"}] }`. |
| `page` | `{ "title": str, "slug": str, "body_class": str, "styles": [href], "scripts": [{src,...}], "relative_root": str }`. |
| `document` | `{ "title": str, "slug": str }` describing the content item. |
| `article` | `{ "summary": str, "meta_items": [str], "tags": [str], "hero": {"url", "alt"}?, "body_html": Markup, "back": {"href","label"}, "footer": {"href","copy"} }`. |
| `gallery` | `{ "loading_message": str }` supplied when rendering `pages/gallery.html`. |
| `music` | `{ "loading_message": str }` supplied when rendering `pages/music.html`. |
| `shell` | `{ "theme": str, "data_attributes": { "site-config": str, ... } }` seeds theme toggle + data attributes. |
| `assets` | Dict built from the manifest (`styles`, `scripts`). |
| `feeds` | Convenience mapping for `/feed.xml`, `/atom.xml`, `/feed.json`. |

`base.html` serialises `shell.data_attributes` into `data-*` attributes on `#app-shell`. The inline script installs `window.__SMILE_DATA__` so front-end code can hydrate using the same URL sets regardless of the page depth.

## Extending or Creating Themes

1. Copy `web/themes/default/` to a new directory (e.g., `web/themes/my-theme/`).
2. Update `theme.json` with a unique name and adjust `entrypoints`, `partials`, or assets as needed.
3. Modify `base.html`, partials, and page templates to customise layout and styling.
4. Point the build configuration at the new theme:
   ```yaml
   # smilecms.yml
   templates_dir: web
   theme_name: my-theme
   ```
   or via CLI overrides if available.
5. Run the build (`python -m src.cli build`) and inspect the output under `site/`.

All templates are standard Jinja2 files. Autoescaping is enabled, so wrap trusted HTML in `|safe` when necessary (for example, when rendering Markdown that has already been sanitised).

## Inline Script Responsibilities

`partials/inline-script.html` keeps the behaviour that was previously injected by Python:

- Applies the theme stored on `#app-shell` to the document element.
- Toggles light/dark mode and nav visibility via accessible controls.
- Boots `window.__SMILE_DATA__` with manifest/site-config endpoints drawn from template context.

Feel free to break this into separate modules or bundle it as part of your asset pipeline—update `assets.scripts` and the partial accordingly.

## Testing Themes

The regression suite (`tests/test_articles.py`) includes snapshot-style assertions that ensure rendered pages expose navigation, assets, inline scripts, and back links. When adding new templates or context keys:

1. Update the tests to cover visible changes or new data attributes.
2. Run `pytest tests/test_articles.py` (or the full suite) to confirm behaviour.
3. Consider adding dedicated tests for additional page entrypoints if your theme introduces them.

This guide will evolve as additional pages move to the theme system. Contributions and improvements are welcome—keep documentation in sync with template changes so theme authors can iterate quickly.
