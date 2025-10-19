"""Shared Markdown rendering helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import cast

from markdown_it import MarkdownIt
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin


@lru_cache(maxsize=1)
def _renderer() -> MarkdownIt:
    """Configure and cache a CommonMark-compliant renderer."""
    md = MarkdownIt("commonmark", {"html": True, "linkify": True, "typographer": True})
    md.enable("table").enable("strikethrough")
    md.use(deflist_plugin)
    md.use(footnote_plugin)
    md.use(tasklists_plugin, label=True)
    return md


def render_markdown(text: str) -> str:
    """Render Markdown to HTML using the shared renderer."""
    if not text.strip():
        return ""
    return cast(str, _renderer().render(text))
