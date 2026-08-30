"""Installed-command integration tests for site2md."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

Response = tuple[int, dict[str, str], bytes]


class RecordingServer:
    """Serve fixed responses and record every requested path."""

    def __init__(self, routes: dict[str, Response]) -> None:
        self.requests: list[str] = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                requests.append(self.path)
                route = routes.get(self.path)
                if route is None:
                    response = (404, {"Content-Type": "text/plain"}, b"not found")
                else:
                    response = route

                status, headers, body = response
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def origin(self) -> str:
        """Return this server's HTTP origin."""
        host, port = self.httpd.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> RecordingServer:
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()


class Site2mdCliTests(unittest.TestCase):
    """Exercise remote and local conversion through the installed CLI."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.command = Path(sys.executable).with_name("site2md")
        if not cls.command.is_file():
            raise RuntimeError(f"Installed site2md command not found at {cls.command}")

    def run_site2md(self, *arguments: object, without_wget: bool = False) -> subprocess.CompletedProcess[str]:
        """Run the installed command and capture its observable result."""
        env = os.environ.copy()
        if without_wget:
            env["PATH"] = str(self.command.parent)
        return subprocess.run(
            [str(self.command), *map(str, arguments)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    @staticmethod
    def link_rich_html() -> bytes:
        return b"""<!doctype html>
<html>
<head><meta charset="utf-8"><base href="/catalog/"></head>
<body><main>
<h1>Available homes</h1>
<a href="filters?radius=10">Filter</a>
<a href="?page=2">Next page</a>
<a href="listing/42">Listing</a>
<a href="#details">Details section</a>
<a href="mailto:agent@example.com">Email</a>
<a href="tel:+4912345">Telephone</a>
<img src="images/home.jpg" alt="Home">
<h2 id="details">Details</h2>
</main></body>
</html>"""

    def assert_link_rich_page(self, markdown: str, origin: str) -> None:
        """Assert page-mode URL normalization in generated Markdown."""
        self.assertIn(f"<!-- Source: {origin}/results -->", markdown)
        self.assertIn(f"[Filter]({origin}/catalog/filters?radius=10)", markdown)
        self.assertIn(f"[Next page]({origin}/catalog/?page=2)", markdown)
        self.assertIn(f"[Listing]({origin}/catalog/listing/42)", markdown)
        self.assertIn("[Details section](#details)", markdown)
        self.assertIn("[Email](mailto:agent@example.com)", markdown)
        self.assertIn("[Telephone](tel:+4912345)", markdown)
        self.assertIn(f"![Home]({origin}/catalog/images/home.jpg)", markdown)

    def test_explicit_page_mode_fetches_only_the_requested_document(self) -> None:
        with RecordingServer(
            {"/results": (200, {"Content-Type": "text/html; charset=utf-8"}, self.link_rich_html())}
        ) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.md"

            result = self.run_site2md(
                "build", f"{server.origin}/results", "--mode", "page", "--output", output
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(server.requests, ["/results"])
            self.assertTrue(output.is_file())
            self.assert_link_rich_page(output.read_text(encoding="utf-8"), server.origin)

    def test_page_mode_is_default_and_does_not_require_wget(self) -> None:
        with RecordingServer(
            {"/results": (200, {"Content-Type": "text/html; charset=utf-8"}, self.link_rich_html())}
        ) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.md"

            result = self.run_site2md(
                "build", f"{server.origin}/results", "--output", output, without_wget=True
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(server.requests, ["/results"])
            self.assert_link_rich_page(output.read_text(encoding="utf-8"), server.origin)

    def test_redirect_uses_final_url_for_source_and_relative_links(self) -> None:
        html = b'<html><body><main><a href="child.html">Child</a></main></body></html>'
        routes: dict[str, Response] = {
            "/start": (302, {"Location": "/final/page.html"}, b""),
            "/final/page.html": (200, {"Content-Type": "text/html"}, html),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "redirect.md"

            result = self.run_site2md("build", f"{server.origin}/start", "--output", output)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(server.requests, ["/start", "/final/page.html"])
            markdown = output.read_text(encoding="utf-8")
            self.assertIn(f"<!-- Source: {server.origin}/final/page.html -->", markdown)
            self.assertIn(f"[Child]({server.origin}/final/child.html)", markdown)

    def test_response_and_document_encoding_metadata_are_honored(self) -> None:
        http_declared = "<html><body><main><p>caf\u00e9</p></main></body></html>".encode("iso-8859-1")
        meta_declared = (
            '<html><head><meta charset="windows-1252"></head>'
            '<body><main><p>Price \u20ac10</p></main></body></html>'
        ).encode("windows-1252")
        routes: dict[str, Response] = {
            "/http-encoding": (
                200,
                {"Content-Type": "text/html; charset=iso-8859-1"},
                http_declared,
            ),
            "/meta-encoding": (200, {"Content-Type": "text/html"}, meta_declared),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            cases = [("http-encoding", "caf\u00e9"), ("meta-encoding", "Price \u20ac10")]
            for path, expected in cases:
                with self.subTest(path=path):
                    output = Path(temp_dir) / f"{path}.md"
                    result = self.run_site2md(
                        "build", f"{server.origin}/{path}", "--output", output
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(expected, output.read_text(encoding="utf-8"))

    def test_unimplemented_modes_are_rejected_without_fetching(self) -> None:
        with RecordingServer({}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.md"

            result = self.run_site2md(
                "build", f"{server.origin}/results", "--mode", "follow", "--output", output
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(server.requests, [])
            self.assertFalse(output.exists())

    def test_local_directory_conversion_keeps_discovery_and_source_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "input"
            nested = root / "nested"
            nested.mkdir(parents=True)
            (root / "index.html").write_text(
                "<html><body><main><h1>Index</h1></main></body></html>", encoding="utf-8"
            )
            (root / "guide.html").write_text(
                "<html><body><main><h1>Guide</h1></main></body></html>", encoding="utf-8"
            )
            (nested / "chapter.html").write_text(
                "<html><body><main><h1>Chapter</h1></main></body></html>", encoding="utf-8"
            )
            output = Path(temp_dir) / "local.md"

            result = self.run_site2md("build", root, "--output", output)

            self.assertEqual(result.returncode, 0, result.stderr)
            markdown = output.read_text(encoding="utf-8")
            sources = [
                "<!-- Source: index.html -->",
                "<!-- Source: guide.html -->",
                "<!-- Source: chapter.html -->",
            ]
            positions = [markdown.index(source) for source in sources]
            self.assertEqual(positions, sorted(positions))
            self.assertEqual(markdown.count("\n\n---\n\n"), 3)


if __name__ == "__main__":
    unittest.main()
