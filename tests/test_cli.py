"""Installed-command integration tests for site2md."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from typing_extensions import Self

Response = tuple[int, dict[str, str], bytes]
Route = Union[Response, Callable[[BaseHTTPRequestHandler], None]]


class RecordingServer:
    """Serve fixed responses and record every requested path."""

    def __init__(self, routes: Mapping[str, Route]) -> None:
        self.requests: list[str] = []
        self.user_agents: list[str | None] = []
        requests = self.requests
        user_agents = self.user_agents

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                requests.append(self.path)
                user_agents.append(self.headers.get("User-Agent"))
                route = routes.get(self.path)
                if route is None:
                    response = (404, {"Content-Type": "text/plain"}, b"not found")
                elif callable(route):
                    route(self)
                    return
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
        return f"http://{self.httpd.server_name}:{self.httpd.server_port}"

    def __enter__(self) -> Self:
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()


class Site2mdCliTests(unittest.TestCase):
    """Exercise remote and local conversion through the installed CLI."""

    command: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.command = Path(sys.executable).with_name("site2md")
        if not cls.command.is_file():
            raise RuntimeError(f"Installed site2md command not found at {cls.command}")

    def run_site2md(
        self,
        *arguments: object,
        without_wget: bool = False,
        timeout: float | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the installed command and capture its observable result."""
        env = os.environ.copy()
        if without_wget:
            env["PATH"] = str(self.command.parent)
        if extra_environment:
            env.update(extra_environment)
        return subprocess.run(
            [str(self.command), *map(str, arguments)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )

    @staticmethod
    def startup_hook_environment(root: Path, source: str) -> dict[str, str]:
        """Create a subprocess-only Python startup hook."""
        hook_dir = root / "startup-hook"
        hook_dir.mkdir()
        (hook_dir / "sitecustomize.py").write_text(source, encoding="utf-8")
        python_path = os.environ.get("PYTHONPATH")
        if python_path:
            hook_path = f"{hook_dir}{os.pathsep}{python_path}"
        else:
            hook_path = str(hook_dir)
        return {"PYTHONPATH": hook_path}

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

    @staticmethod
    def valid_html(text: str = "ok") -> bytes:
        """Return a minimal HTML page containing text."""
        return f"<html><body><main><p>{text}</p></main></body></html>".encode()

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

    def assert_failed_without_replacing_output(
        self, result: subprocess.CompletedProcess[str], output: Path
    ) -> None:
        """Assert a failed conversion preserved the prior destination contents."""
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_text(encoding="utf-8"), "previous")

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
            self.assertEqual(server.user_agents, ["site2md/0.3.0"])
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

    def test_default_and_explicit_page_modes_produce_identical_content(self) -> None:
        routes = {
            "/results": (
                200,
                {"Content-Type": "text/html; charset=utf-8"},
                self.link_rich_html(),
            )
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            default_output = Path(temp_dir) / "default.md"
            explicit_output = Path(temp_dir) / "explicit.md"

            default_result = self.run_site2md(
                "build", f"{server.origin}/results", "--output", default_output
            )
            explicit_result = self.run_site2md(
                "build",
                f"{server.origin}/results",
                "--mode",
                "page",
                "--output",
                explicit_output,
            )

            self.assertEqual(default_result.returncode, 0, default_result.stderr)
            self.assertEqual(explicit_result.returncode, 0, explicit_result.stderr)
            self.assertEqual(default_output.read_bytes(), explicit_output.read_bytes())

    def test_page_mode_converts_the_complete_cleaned_body(self) -> None:
        html = b"""<html><body>
<p>Content before the main element.</p>
<main><p>Content inside the main element.</p></main>
<aside><p>Content after the main element.</p></aside>
</body></html>"""
        routes = {"/complete": (200, {"Content-Type": "text/html"}, html)}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "complete.md"

            result = self.run_site2md(
                "build", f"{server.origin}/complete", "--output", output
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            markdown = output.read_text(encoding="utf-8")
            self.assertIn("Content before the main element.", markdown)
            self.assertIn("Content inside the main element.", markdown)
            self.assertIn("Content after the main element.", markdown)

    def test_remote_conversion_failure_does_not_replace_output(self) -> None:
        routes = {"/page": (200, {"Content-Type": "text/html"}, self.valid_html())}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            output = temp_root / "result.md"
            output.write_text("previous", encoding="utf-8")
            environment = self.startup_hook_environment(
                temp_root,
                """from site2md import converter

def fail_markdown_conversion(*args, **kwargs):
    raise RuntimeError("forced conversion failure")

converter.md = fail_markdown_conversion
""",
            )

            result = self.run_site2md(
                "build",
                f"{server.origin}/page",
                "--output",
                output,
                extra_environment=environment,
            )

            self.assert_failed_without_replacing_output(result, output)
            self.assertIn("Error converting remote page:", result.stdout)
            self.assertIn("forced conversion failure", result.stdout)
            self.assertNotIn("Traceback", result.stderr)

    def test_explicit_positive_page_size_limit_overrides_default(self) -> None:
        routes = {"/small": (200, {"Content-Type": "text/html"}, self.valid_html("small"))}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "small.md"

            result = self.run_site2md(
                "build", f"{server.origin}/small", "--max-page-size-mib", "1", "--output", output
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("small", output.read_text(encoding="utf-8"))

    def test_invalid_page_size_values_are_rejected_before_conversion(self) -> None:
        with RecordingServer({"/ok": (200, {"Content-Type": "text/html"}, self.valid_html())}) as server:
            for value in ["0", "-1", "abc"]:
                with self.subTest(value=value):
                    result = self.run_site2md(
                        "build", f"{server.origin}/ok", "--max-page-size-mib", value
                    )
                    self.assertNotEqual(result.returncode, 0)
            self.assertEqual(server.requests, [])

    def test_page_size_option_is_rejected_for_local_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "input"
            root.mkdir()
            (root / "index.html").write_text("<html><body>local</body></html>", encoding="utf-8")
            output = Path(temp_dir) / "local.md"

            for value in ["1", "25"]:
                with self.subTest(value=value):
                    result = self.run_site2md(
                        "build", root, "--max-page-size-mib", value, "--output", output
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())

    def test_declared_oversized_response_fails_without_replacing_output(self) -> None:
        routes = {
            "/huge": (
                200,
                {"Content-Type": "text/html", "Content-Length": str(2 * 1024 * 1024)},
                b"<html></html>",
            )
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"
            output.write_text("previous", encoding="utf-8")

            result = self.run_site2md(
                "build", f"{server.origin}/huge", "--max-page-size-mib", "1", "--output", output
            )

            self.assert_failed_without_replacing_output(result, output)
            self.assertIn("exceeding", result.stdout)

    def test_streaming_oversized_response_fails_without_unbounded_read(self) -> None:
        chunks_sent = []

        def stream(handler: BaseHTTPRequestHandler) -> None:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html")
            handler.end_headers()
            for _ in range(20):
                chunks_sent.append(1)
                try:
                    handler.wfile.write(b"x" * 65536)
                    handler.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
                time.sleep(0.01)

        with RecordingServer({"/stream": stream}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "stream.md"
            output.write_text("previous", encoding="utf-8")

            result = self.run_site2md(
                "build", f"{server.origin}/stream", "--max-page-size-mib", "1", "--output", output
            )

            self.assert_failed_without_replacing_output(result, output)
            self.assertLess(len(chunks_sent), 20)

    def test_slow_response_uses_timeout_without_retries(self) -> None:
        def slow(handler: BaseHTTPRequestHandler) -> None:
            time.sleep(1)
            try:
                handler.send_response(200)
                handler.send_header("Content-Type", "text/html")
                handler.end_headers()
                handler.wfile.write(self.valid_html("late"))
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                pass

        with RecordingServer({"/slow": slow}) as server, tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            output = temp_root / "slow.md"
            output.write_text("previous", encoding="utf-8")
            environment = self.startup_hook_environment(
                temp_root,
                """from site2md import downloader

downloader.REQUEST_TIMEOUT_SECONDS = 0.2
""",
            )

            result = self.run_site2md(
                "build",
                f"{server.origin}/slow",
                "--output",
                output,
                timeout=3,
                extra_environment=environment,
            )

            self.assert_failed_without_replacing_output(result, output)
            self.assertEqual(server.requests, ["/slow"])
            self.assertIn("timed out", result.stdout.lower())

    def test_invalid_final_responses_fail_without_replacing_output(self) -> None:
        routes = {
            "/empty": (200, {"Content-Type": "text/html"}, b""),
            "/json": (200, {"Content-Type": "application/json"}, b"{}"),
            "/missing": (404, {"Content-Type": "text/html"}, self.valid_html()),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            for path in routes:
                with self.subTest(path=path):
                    output = Path(temp_dir) / f"{path.strip('/')}.md"
                    output.write_text("previous", encoding="utf-8")
                    result = self.run_site2md("build", f"{server.origin}{path}", "--output", output)
                    self.assert_failed_without_replacing_output(result, output)

    def test_redirect_uses_final_url_for_source_and_relative_links(self) -> None:
        html = b'<html><body><main><a href="child.html">Child</a></main></body></html>'
        routes: dict[str, Route] = {
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

    def test_cross_origin_redirect_is_allowed(self) -> None:
        with RecordingServer(
            {"/final": (200, {"Content-Type": "text/html"}, self.valid_html("final"))}
        ) as final_server:
            routes = {"/start": (302, {"Location": f"{final_server.origin}/final"}, b"")}
            with RecordingServer(routes) as start_server, tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "redirect.md"

                result = self.run_site2md("build", f"{start_server.origin}/start", "--output", output)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(start_server.requests, ["/start"])
                self.assertEqual(final_server.requests, ["/final"])
                self.assertIn("final", output.read_text(encoding="utf-8"))

    def test_https_to_http_redirect_policy_rejects_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            output = temp_root / "redirect.md"
            output.write_text("previous", encoding="utf-8")
            environment = self.startup_hook_environment(
                temp_root,
                """import io
import urllib.request
from email.message import Message
from urllib.response import addinfourl

class RedirectingHTTPSHandler(urllib.request.BaseHandler):
    def https_open(self, request):
        headers = Message()
        headers["Location"] = "http://example.test/final"
        response = addinfourl(io.BytesIO(b""), headers, request.full_url, 302)
        response.msg = "Found"
        return response

urllib.request.HTTPSHandler = RedirectingHTTPSHandler
""",
            )

            result = self.run_site2md(
                "build",
                "https://example.test/start",
                "--output",
                output,
                timeout=3,
                extra_environment=environment,
            )

            self.assert_failed_without_replacing_output(result, output)
            self.assertIn("Refusing HTTPS-to-HTTP redirect downgrade.", result.stdout)

    def test_keep_temp_controls_failed_fetch_artifacts(self) -> None:
        def stream(handler: BaseHTTPRequestHandler) -> None:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html")
            handler.end_headers()
            for _ in range(20):
                try:
                    handler.wfile.write(b"x" * 65536)
                    handler.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break

        routes: dict[str, Route] = {"/stream": stream}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"
            output.write_text("previous", encoding="utf-8")

            result = self.run_site2md(
                "build", f"{server.origin}/stream", "--max-page-size-mib", "1", "--output", output
            )

            self.assert_failed_without_replacing_output(result, output)
            self.assertNotIn("Temporary files kept at", result.stdout)

            kept_result = self.run_site2md(
                "build",
                f"{server.origin}/stream",
                "--max-page-size-mib",
                "1",
                "--output",
                output,
                "--keep-temp",
            )

            self.assert_failed_without_replacing_output(kept_result, output)
            marker = "Temporary files kept at "
            self.assertIn(marker, kept_result.stdout)
            kept_dir = Path(kept_result.stdout.split(marker, 1)[1].splitlines()[0].strip())
            self.assertTrue(kept_dir.is_dir())
            self.assertGreater((kept_dir / "page.html").stat().st_size, 0)

    def test_keep_temp_reports_successful_remote_build_artifacts(self) -> None:
        routes = {"/page": (200, {"Content-Type": "text/html"}, self.valid_html())}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            result = self.run_site2md(
                "build", f"{server.origin}/page", "--output", output, "--keep-temp"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            marker = "Temporary files kept at "
            self.assertIn(marker, result.stdout)
            kept_dir = Path(result.stdout.split(marker, 1)[1].splitlines()[0].strip())
            self.addCleanup(shutil.rmtree, kept_dir, ignore_errors=True)
            self.assertTrue((kept_dir / "page.html").is_file())
            self.assertTrue((kept_dir / "converted.md").is_file())

    def test_default_success_removes_remote_workspace(self) -> None:
        routes = {"/page": (200, {"Content-Type": "text/html"}, self.valid_html())}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace_root = temp_root / "workspaces"
            workspace_root.mkdir()
            output = temp_root / "out.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/page",
                "--output",
                output,
                extra_environment={"TMPDIR": str(workspace_root)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(workspace_root.iterdir()), [])

    def test_destination_write_failure_preserves_existing_output(self) -> None:
        routes = {"/page": (200, {"Content-Type": "text/html"}, self.valid_html())}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            output = temp_root / "out.md"
            output.write_text("previous", encoding="utf-8")
            environment = self.startup_hook_environment(
                temp_root,
                """from site2md import remote_build

def fail_destination_replace(*args, **kwargs):
    raise OSError("forced destination failure")

remote_build.os.replace = fail_destination_replace
""",
            )

            result = self.run_site2md(
                "build",
                f"{server.origin}/page",
                "--output",
                output,
                extra_environment=environment,
            )

            self.assert_failed_without_replacing_output(result, output)
            self.assertIn("forced destination failure", result.stdout)
            self.assertNotIn("Traceback", result.stderr)

    def test_interruption_preserves_existing_output_and_cleans_workspace(self) -> None:
        routes = {"/page": (200, {"Content-Type": "text/html"}, self.valid_html())}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace_root = temp_root / "workspaces"
            workspace_root.mkdir()
            output = temp_root / "out.md"
            output.write_text("previous", encoding="utf-8")
            environment = self.startup_hook_environment(
                temp_root,
                """from site2md import converter

def interrupt_conversion(*args, **kwargs):
    raise KeyboardInterrupt()

converter.md = interrupt_conversion
""",
            )
            environment["TMPDIR"] = str(workspace_root)

            result = self.run_site2md(
                "build",
                f"{server.origin}/page",
                "--output",
                output,
                extra_environment=environment,
            )

            self.assert_failed_without_replacing_output(result, output)
            self.assertEqual(list(workspace_root.iterdir()), [])

    def test_keep_temp_reports_interrupted_workspace(self) -> None:
        routes = {"/page": (200, {"Content-Type": "text/html"}, self.valid_html())}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace_root = temp_root / "workspaces"
            workspace_root.mkdir()
            output = temp_root / "out.md"
            output.write_text("previous", encoding="utf-8")
            environment = self.startup_hook_environment(
                temp_root,
                """from site2md import converter

def interrupt_conversion(*args, **kwargs):
    raise KeyboardInterrupt()

converter.md = interrupt_conversion
""",
            )
            environment["TMPDIR"] = str(workspace_root)

            result = self.run_site2md(
                "build",
                f"{server.origin}/page",
                "--output",
                output,
                "--keep-temp",
                extra_environment=environment,
            )

            self.assert_failed_without_replacing_output(result, output)
            marker = "Temporary files kept at "
            self.assertIn(marker, result.stdout)
            kept_dir = Path(result.stdout.split(marker, 1)[1].splitlines()[0].strip())
            self.assertTrue((kept_dir / "page.html").is_file())
            self.assertNotIn("Traceback", result.stderr)

    def test_failed_cleanup_reports_leaked_workspace(self) -> None:
        routes = {"/page": (200, {"Content-Type": "text/html"}, self.valid_html())}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace_root = temp_root / "workspaces"
            workspace_root.mkdir()
            output = temp_root / "out.md"
            output.write_text("previous", encoding="utf-8")
            environment = self.startup_hook_environment(
                temp_root,
                """from site2md import converter, remote_build

def fail_conversion(*args, **kwargs):
    raise RuntimeError("forced conversion failure")

def fail_cleanup(*args, **kwargs):
    raise OSError("forced cleanup failure")

converter.md = fail_conversion
remote_build.shutil.rmtree = fail_cleanup
""",
            )
            environment["TMPDIR"] = str(workspace_root)

            result = self.run_site2md(
                "build",
                f"{server.origin}/page",
                "--output",
                output,
                extra_environment=environment,
            )

            self.assert_failed_without_replacing_output(result, output)
            self.assertIn("forced conversion failure", result.stdout)
            self.assertIn("forced cleanup failure", result.stdout)
            marker = "Temporary files kept at "
            self.assertIn(marker, result.stdout)
            leaked_dir = Path(result.stdout.split(marker, 1)[1].splitlines()[0].strip())
            self.assertTrue(leaked_dir.is_dir())
            self.assertNotIn("Traceback", result.stderr)

    def test_response_and_document_encoding_metadata_are_honored(self) -> None:
        http_declared = "<html><body><main><p>caf\u00e9</p></main></body></html>".encode("iso-8859-1")
        meta_declared = (
            '<html><head><meta charset="windows-1252"></head>'
            '<body><main><p>Price \u20ac10</p></main></body></html>'
        ).encode("windows-1252")
        routes: dict[str, Route] = {
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
