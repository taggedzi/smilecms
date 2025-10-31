"""Reusable preview server utilities for SmileCMS GUI and CLI.

This module extracts the preview HTTP server helpers so they can be reused
outside the Typer CLI and started/stopped from a GUI thread safely.
"""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterator


class _ThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_request_handler(directory: Path) -> type[SimpleHTTPRequestHandler]:
    """Create a request handler rooted at ``directory`` with sensible MIME types."""
    directory_path = str(directory)

    class PreviewRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=directory_path, **kwargs)

        # Ensure correct Content-Type headers for common static assets during preview.
        extensions_map = dict(SimpleHTTPRequestHandler.extensions_map)
        extensions_map.update(
            {
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
                ".json": "application/json; charset=utf-8",
                ".jsonl": "application/json; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".mp3": "audio/mpeg",
                ".m4a": "audio/mp4",
                ".aac": "audio/aac",
                ".flac": "audio/flac",
                ".ogg": "audio/ogg",
                ".wav": "audio/wav",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
            }
        )

    return PreviewRequestHandler


@contextlib.contextmanager
def serve(
    host: str,
    port: int,
    handler: type[SimpleHTTPRequestHandler],
) -> Iterator[ThreadingHTTPServer]:
    """Context manager that creates and cleans up the HTTP server."""
    server = _ThreadingHTTPServer((host, port), handler)
    try:
        yield server
    finally:
        try:
            server.shutdown()
        finally:
            server.server_close()


@dataclass(slots=True)
class PreviewServerHandle:
    server: ThreadingHTTPServer
    thread: threading.Thread
    host: str
    port: int


def _run_forever(server: ThreadingHTTPServer) -> None:
    try:
        server.serve_forever()
    except Exception:
        # Let the owning code decide how to surface errors.
        pass


def start_preview(
    directory: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    max_attempts: int = 20,
) -> PreviewServerHandle:
    """Start the preview server in a background thread.

    Tries ``port`` and increments until a free port is found, up to ``max_attempts``.
    Returns a handle that can be passed to ``stop_preview``.
    """
    directory = directory.resolve()
    handler = make_request_handler(directory)

    attempt = 0
    last_exc: Exception | None = None
    while attempt <= max_attempts:
        try:
            server = _ThreadingHTTPServer((host, port + attempt), handler)
            # Determine the bound address (handles 0.0.0.0 and bytes cases)
            raw_host = server.server_address[0]
            bound_host = (
                raw_host.decode("utf-8", "ignore") if isinstance(raw_host, bytes) else str(raw_host)
            )
            bound_port = int(server.server_address[1])
            th = threading.Thread(target=_run_forever, args=(server,), daemon=True)
            th.start()
            return PreviewServerHandle(server=server, thread=th, host=bound_host, port=bound_port)
        except OSError as exc:  # port busy or permission error
            last_exc = exc
            attempt += 1

    # If we get here, we failed to bind any port in the range
    if last_exc:
        raise last_exc
    raise OSError("Unable to bind preview server to the requested port range")


def stop_preview(handle: PreviewServerHandle | None) -> None:
    """Stop a running preview server started by ``start_preview``."""
    if handle is None:
        return
    try:
        handle.server.shutdown()
    finally:
        handle.server.server_close()
    if handle.thread.is_alive():
        handle.thread.join(timeout=2.0)

