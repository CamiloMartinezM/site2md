"""Serve the benchmark's fixtures on 127.0.0.1 and record every request."""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing_extensions import Self

ALLOW_EVERYTHING = b"User-agent: *\nAllow: /\n"


class FixtureServer:
    """Serve fixed HTML pages on a free port, and record the time and path of each request."""

    def __init__(self, pages: Mapping[str, bytes]) -> None:
        self.requests: list[tuple[float, str]] = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                requests.append((time.monotonic(), self.path))
                content_type = "text/html; charset=utf-8"
                body = pages.get(self.path)
                if body is None and self.path == "/robots.txt":
                    content_type, body = "text/plain; charset=utf-8", ALLOW_EVERYTHING
                status = 200
                if body is None:
                    status, content_type, body = 404, "text/plain; charset=utf-8", b"not found"
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        # Port 0 lets the system pick a free port, so parallel runs never collide.
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        # A short poll interval keeps shutdown from waiting half a second.
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )

    @property
    def origin(self) -> str:
        """Return this server's HTTP origin."""
        return f"http://127.0.0.1:{self._httpd.server_port}"

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join()
