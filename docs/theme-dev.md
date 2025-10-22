# Theme Development Guide

SmileCMS ships with a Jinja2-based theming system that keeps presentation concerns separate from the Python build pipeline. This guide explains the default layout, how templates are loaded, and which context objects are injected when rendering pages.

## Directory Layout

Site themes now live under `web/<site-theme>/`. Each site theme bundles the static assets and metadata that are copied into the generated site. The default theme resides at `web/dark-theme-1/` and contains:

- `config/` - site metadata such as `site.json`.
- `gallery/`, `journal/`, `music/`, `styles/`, `templates/` - static assets staged verbatim.
- `js/` - browser entrypoints referenced by the layout.
- `themes/default/` - the Jinja theme that drives templated pages.
- `index.html` - static files published at the site root.

During a build SmileCMS resolves the active site theme using two configuration values:

- `Config.templates_dir` points at the directory that holds available site themes. The default value is `web/dark-theme-1/` so existing installs continue to work.
- `Config.site_theme` (optional) names a subdirectory of `templates_dir` to stage. When unset, `templates_dir` is treated as the already-resolved theme directory.

Within a site theme, the renderer still loads Jinja templates from `<resolved_templates_dir>/themes`. Set `Config.theme_name` to switch the active Jinja theme while keeping the surrounding static assets. If the requested theme is missing or incomplete, SmileCMS automatically falls back to the bundled `default` theme.

## Manifest Schema

`theme.json` follows the structure validated by `src.themes.ThemeManifest`:

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

- **entrypoints** map page names (for example `article`, `gallery`) to template files. `base` is required.
- **partials** are optional helpers included by `base.html`. Missing partials are simply skipped.
- **assets.styles** is an ordered list of stylesheet URLs.
- **assets.scripts** contains objects with `src` plus optional `type`, `defer`, `async`, `integrity`, and `crossorigin`.
- **default_shell_theme** is applied when no explicit theme is set on the rendered page.

If a custom theme omits styles or scripts, the loader reuses values from the fallback theme.

## Template Context

All page entrypoints inherit a shared context surface; individual pages (for example `article`, `gallery`, `music`) add their own blocks under the keys noted below.

| Key | Description |
| --- | --- |
| `site` | `{ "title": str, "tagline": str }` calculated from `config/site.json`. |
| `navigation` | `{ "items": [{"label", "href", "active"}], "menu_open": bool }`. |
| `footer` | `{ "copy": str, "links": [{"label", "href", "external"}] }`. |
| `page` | `{ "title": str, "slug": str, "body_class": str, "styles": [href], "scripts": [{src,...}], "relative_root": str }`. |
| `document` | `{ "title": str, "slug": str }` describing the content item. |
| `article` | `{ "summary": str, "meta_items": [str], "tags": [str], "hero": {"url", "alt"}?, "body_html": Markup, "back": {"href","label"}, "footer": {"href","copy"} }`. |
| `gallery` | `{ "loading_message": str }` supplied when rendering `pages/gallery.html`. |
| `music` | `{ "loading_message": str }` supplied when rendering `pages/music.html`. |
| `shell` | `{ "theme": str, "data_attributes": { "site-config": str, ... } }` seeds theme-related data attributes. |
| `assets` | Dictionary derived from the manifest (`styles`, `scripts`). |
| `feeds` | Convenience mapping for `/feed.xml`, `/atom.xml`, `/feed.json`. |

`base.html` serialises `shell.data_attributes` into `data-*` attributes on `#app-shell`. The inline script installs `window.__SMILE_DATA__` so front-end code can hydrate using the same URL sets regardless of page depth.

## Extending or Creating Themes

1. Copy the default site theme (`web/dark-theme-1/`) to a new directory (for example `web/future-neon/`).
2. Update static assets and metadata inside the copied directory as needed.
3. Modify the Jinja theme under `<your-theme>/themes/` and adjust `theme.json` with the desired entrypoints or assets.
4. Point the build configuration at the new site theme:
   ```yaml
   # smilecms.yml
   templates_dir: web
   site_theme: future-neon
   theme_name: default
   ```
   You can also override `site_theme` or `theme_name` via CLI options if available.
5. Run the build (`python -m src.cli build`) and inspect the output under `site/`.

## Inline Script Responsibilities

`partials/inline-script.html` keeps behaviour that was previously injected by Python:

- Applies the theme stored on `#app-shell` to the document element.
- Toggles light/dark mode and navigation visibility via accessible controls.
- Boots `window.__SMILE_DATA__` with manifest and site-config endpoints drawn from template context.

Feel free to split this script into separate modules or bundle it through your asset pipeline. Update `assets.scripts` and the partial itself accordingly.

## Testing Themes

The regression suite (`tests/test_articles.py`) includes assertions that ensure rendered pages expose navigation, assets, inline scripts, and back links. When adding new templates or context keys:

1. Update the tests to cover visible changes or new data attributes.
2. Run `pytest tests/test_articles.py` (or the full suite) to confirm behaviour.
3. Consider adding dedicated tests for additional page entrypoints if your theme introduces them.

Keep this guide in sync with template changes so theme authors can iterate quickly.
