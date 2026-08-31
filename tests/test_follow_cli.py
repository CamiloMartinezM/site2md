"""Installed-command acceptance tests for one-hop follow mode."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
import unittest
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from tests.cli_test_support import InstalledCliTestCase, RecordingServer, Route


class FollowModeCliTests(InstalledCliTestCase):
    """Exercise follow mode through the installed command and real HTTP."""

    def test_follow_selector_converts_one_hop_in_document_order(self) -> None:
        entry = b"""<html><body><main>
<a class="detail" href="/second">Second</a>
<a class="detail" href="/first">First</a>
</main></body></html>"""
        child = b"""<html><body><main>
<p>child content</p><a class="detail" href="/grandchild">Grandchild</a>
</main></body></html>"""
        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/second": (200, {"Content-Type": "text/html"}, child),
            "/first": (200, {"Content-Type": "text/html"}, child),
            "/grandchild": (200, {"Content-Type": "text/html"}, child),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "follow.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a.detail",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                server.requests,
                ["/entry", "/robots.txt", "/second", "/first"],
            )
            markdown = output.read_text(encoding="utf-8")
            sources = [
                f"<!-- Source: {server.origin}/entry -->",
                f"<!-- Source: {server.origin}/second -->",
                f"<!-- Source: {server.origin}/first -->",
            ]
            self.assertEqual([markdown.index(source) for source in sources], sorted(
                markdown.index(source) for source in sources
            ))
            self.assertIn("Fetched 3; skipped 0; failed 0.", result.stdout)

    def test_follow_selector_union_uses_original_entry_html_and_base_url(self) -> None:
        entry = b"""<html><head><base href="/catalog/"></head><body><main>
<a class="alpha" href="item?b=2&a=1#top" rel="nofollow">Alpha</a>
<a class="beta" href="other">Beta</a>
<a class="beta" href="item?b=2&a=1#details">Duplicate</a>
<div class="beta" href="ignored"><a href="nested">Not directly selected</a></div>
<a class="alpha" href="https://example.invalid/external">External</a>
</main></body></html>"""
        routes: dict[str, Route] = {
            "/start": (302, {"Location": "/final/entry"}, b""),
            "/final/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/catalog/item?b=2&a=1": (
                200,
                {"Content-Type": "text/html"},
                b"<html><body><main><p>alpha page</p></main></body></html>",
            ),
            "/catalog/other": (
                200,
                {"Content-Type": "text/html"},
                b"<html><body><main><p>beta page</p></main></body></html>",
            ),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "follow.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/start",
                "--mode",
                "follow",
                "--follow-selector",
                "a.beta",
                "--follow-selector",
                "a.alpha",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                server.requests,
                [
                    "/start",
                    "/final/entry",
                    "/robots.txt",
                    "/catalog/item?b=2&a=1",
                    "/catalog/other",
                ],
            )
            markdown = output.read_text(encoding="utf-8")
            self.assertLess(markdown.index("alpha page"), markdown.index("beta page"))
            self.assertEqual(markdown.count("/catalog/item?b=2&a=1 -->"), 1)

    def test_page_budget_writes_a_bounded_follow_result(self) -> None:
        entry = b"""<html><body><main>
<a href="/one">One</a><a href="/two">Two</a>
</main></body></html>"""
        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/one": (200, {"Content-Type": "text/html"}, b"<html><body>one</body></html>"),
            "/two": (200, {"Content-Type": "text/html"}, b"<html><body>two</body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "bounded.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--max-pages",
                "2",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(server.requests, ["/entry", "/robots.txt", "/one"])
            self.assertIn("Reached limit: page count (2)", result.stdout)
            markdown = output.read_text(encoding="utf-8")
            self.assertIn("one", markdown)
            self.assertNotIn("<!-- Source: " + server.origin + "/two -->", markdown)

    def test_aggregate_budget_discards_partial_child_and_stops(self) -> None:
        entry = b'<html><body><a href="/large">Large</a><a href="/later">Later</a></body></html>'

        def stream_large(handler: BaseHTTPRequestHandler) -> None:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html")
            handler.end_headers()
            try:
                for _ in range(20):
                    handler.wfile.write(b"x" * 65536)
                    handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/large": stream_large,
            "/later": (200, {"Content-Type": "text/html"}, b"<html><body>later</body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "bounded.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--max-total-size-mib",
                "1",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(server.requests, ["/entry", "/robots.txt", "/large"])
            self.assertIn("Reached limit: aggregate content (1 MiB)", result.stdout)
            self.assertIn("Fetched 1; skipped 2; failed 0.", result.stdout)
            markdown = output.read_text(encoding="utf-8")
            self.assertIn(f"<!-- Source: {server.origin}/entry -->", markdown)
            self.assertNotIn(f"<!-- Source: {server.origin}/large -->", markdown)

    def test_zero_remaining_aggregate_budget_counts_admitted_target_as_skipped(self) -> None:
        prefix = b'<html><body><a href="/child">Child</a><p>'
        suffix = b"</p></body></html>"
        entry = prefix + b"x" * (1024 * 1024 - len(prefix) - len(suffix)) + suffix
        routes = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/child": (200, {"Content-Type": "text/html"}, b"<html><body>child</body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "bounded.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--max-total-size-mib",
                "1",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(server.requests, ["/entry", "/robots.txt"])
            self.assertIn("Reached limit: aggregate content (1 MiB)", result.stdout)
            self.assertIn("Fetched 1; skipped 1; failed 0.", result.stdout)

    def test_discarded_partial_bytes_still_consume_the_aggregate_budget(self) -> None:
        entry = b'<html><body><a href="/per-page">Large</a><a href="/aggregate">Next</a></body></html>'

        def stream_over_page_limit(handler: BaseHTTPRequestHandler) -> None:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html")
            handler.end_headers()
            try:
                for _ in range(20):
                    handler.wfile.write(b"x" * 65536)
                    handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/per-page": stream_over_page_limit,
            "/aggregate": (
                200,
                {"Content-Type": "text/html", "Content-Length": str(1024 * 1024)},
                b"<html><body>must be discarded</body></html>",
            ),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "bounded.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--max-page-size-mib",
                "1",
                "--max-total-size-mib",
                "2",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                server.requests,
                ["/entry", "/robots.txt", "/per-page", "/aggregate"],
            )
            self.assertIn("Reached limit: aggregate content (2 MiB)", result.stdout)
            self.assertIn("Fetched 1; skipped 1; failed 1.", result.stdout)
            self.assertNotIn("must be discarded", output.read_text(encoding="utf-8"))

    def test_follow_selection_failures_preserve_destination_before_child_requests(self) -> None:
        entry = b'<html><body><div class="card"><a href="/child">Child</a></div></body></html>'
        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (200, {"Content-Type": "text/plain"}, b"User-agent: *\nAllow: /"),
            "/child": (200, {"Content-Type": "text/html"}, b"<html><body>child</body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            for name, selector in (("invalid", "a["), ("non-anchor", "div.card")):
                with self.subTest(name=name):
                    output = Path(temp_dir) / f"{name}.md"
                    output.write_text("previous", encoding="utf-8")
                    before = len(server.requests)

                    result = self.run_site2md(
                        "build",
                        f"{server.origin}/entry",
                        "--mode",
                        "follow",
                        "--follow-selector",
                        selector,
                        "--output",
                        output,
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(server.requests[before:], ["/entry"])
                    self.assertEqual(output.read_text(encoding="utf-8"), "previous")

    def test_mode_specific_options_are_rejected_before_network_access(self) -> None:
        with RecordingServer({}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.md"
            cases = (
                ("--mode", "follow"),
                ("--mode", "page", "--follow-selector", "a"),
                ("--mode", "page", "--max-pages", "2"),
                ("--mode", "page", "--max-total-size-mib", "2"),
                ("--mode", "follow", "--follow-selector", "a", "--max-pages", "0"),
                (
                    "--mode",
                    "follow",
                    "--follow-selector",
                    "a",
                    "--max-total-size-mib",
                    "0",
                ),
                ("--mode", "follow", "--follow-selector", "a", "--max-depth", "2"),
            )
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_site2md(
                        "build",
                        f"{server.origin}/entry",
                        *arguments,
                        "--output",
                        output,
                    )
                    self.assertNotEqual(result.returncode, 0)
            self.assertEqual(server.requests, [])

    def test_local_input_rejects_remote_traversal_options(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "input"
            root.mkdir()
            (root / "index.html").write_text("<html><body>local</body></html>", encoding="utf-8")
            output = Path(temp_dir) / "local.md"

            result = self.run_site2md(
                "build",
                root,
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--output",
                output,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

    def test_robots_policy_filters_children_and_controls_request_pacing(self) -> None:
        entry = b"""<html><body>
<a href="/blocked">Blocked</a><a href="/first">First</a><a href="/second">Second</a>
</body></html>"""
        request_times: list[float] = []

        def child(handler: BaseHTTPRequestHandler) -> None:
            request_times.append(time.monotonic())
            body = b"<html><body>allowed</body></html>"
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)

        robots = b"""User-agent: *
Disallow: /blocked
Request-rate: 2/3
"""
        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (200, {"Content-Type": "text/plain"}, robots),
            "/blocked": child,
            "/first": child,
            "/second": child,
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "robots.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                server.requests,
                ["/entry", "/robots.txt", "/first", "/second"],
            )
            self.assertGreaterEqual(request_times[1] - request_times[0], 1.4)
            self.assertIn("Robots policy disallows", result.stdout)
            self.assertIn("Fetched 3; skipped 1; failed 0.", result.stdout)

    def test_robots_crawl_delay_controls_request_pacing(self) -> None:
        entry = b'<html><body><a href="/first">First</a><a href="/second">Second</a></body></html>'
        request_times: list[float] = []

        def child(handler: BaseHTTPRequestHandler) -> None:
            request_times.append(time.monotonic())
            body = b"<html><body>allowed</body></html>"
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)

        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (
                200,
                {"Content-Type": "text/plain"},
                b"User-agent: *\nCrawl-delay: 2\n",
            ),
            "/first": child,
            "/second": child,
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "crawl-delay.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                server.requests,
                ["/entry", "/robots.txt", "/first", "/second"],
            )
            self.assertGreaterEqual(request_times[1] - request_times[0], 1.9)

    def test_redirect_hop_body_is_counted_before_robots_rejects_its_target(self) -> None:
        entry = b'<html><body><a href="/redirect">Redirect</a></body></html>'
        redirect_body = b"non-empty redirect response"
        robots = b"User-agent: *\nDisallow: /blocked\n"
        routes = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (200, {"Content-Type": "text/plain"}, robots),
            "/redirect": (302, {"Location": "/blocked"}, redirect_body),
            "/blocked": (
                200,
                {"Content-Type": "text/html"},
                b"<html><body>must not be requested</body></html>",
            ),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "robots-redirect.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--keep-temp",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(server.requests, ["/entry", "/robots.txt", "/redirect"])
            self.assertIn("Robots policy disallows", result.stdout)
            marker = "Temporary files kept at "
            workspace = Path(result.stdout.split(marker, 1)[1].splitlines()[0].strip())
            self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)
            index = json.loads((workspace / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["pages"][1]["body_bytes"], len(redirect_body))

    def test_redirect_hop_bodies_obey_aggregate_budget_and_request_pacing(self) -> None:
        entry = b'<html><body><a href="/first-hop">Redirect</a></body></html>'
        request_times: list[float] = []
        hop_body = b"x" * (700 * 1024)

        def redirect(location: str) -> Callable[[BaseHTTPRequestHandler], None]:
            def respond(handler: BaseHTTPRequestHandler) -> None:
                request_times.append(time.monotonic())
                handler.send_response(302)
                handler.send_header("Location", location)
                handler.send_header("Content-Length", str(len(hop_body)))
                handler.end_headers()
                handler.wfile.write(hop_body)

            return respond

        robots = b"User-agent: *\nRequest-rate: 2/3\n"
        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (200, {"Content-Type": "text/plain"}, robots),
            "/first-hop": redirect("/second-hop"),
            "/second-hop": redirect("/final"),
            "/final": (200, {"Content-Type": "text/html"}, b"<html><body>final</body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "aggregate-redirect.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--max-page-size-mib",
                "1",
                "--max-total-size-mib",
                "1",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                server.requests,
                ["/entry", "/robots.txt", "/first-hop", "/second-hop"],
            )
            self.assertGreaterEqual(request_times[1] - request_times[0], 1.4)
            self.assertIn("Reached limit: aggregate content (1 MiB)", result.stdout)
            self.assertNotIn("<!-- Source: " + server.origin + "/final -->", output.read_text())

    def test_redirect_hop_body_obeys_per_page_streaming_limit(self) -> None:
        entry = b'<html><body><a href="/redirect">Redirect</a></body></html>'

        def oversized_redirect(handler: BaseHTTPRequestHandler) -> None:
            handler.send_response(302)
            handler.send_header("Location", "/final")
            handler.end_headers()
            try:
                for _ in range(20):
                    handler.wfile.write(b"x" * 65536)
                    handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/redirect": oversized_redirect,
            "/final": (200, {"Content-Type": "text/html"}, b"<html><body>final</body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "page-limit-redirect.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--max-page-size-mib",
                "1",
                "--max-total-size-mib",
                "3",
                "--keep-temp",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(server.requests, ["/entry", "/robots.txt", "/redirect"])
            self.assertIn("Fetched 1; skipped 0; failed 1.", result.stdout)
            self.assertIn("1 MiB limit", result.stdout)
            marker = "Temporary files kept at "
            workspace = Path(result.stdout.split(marker, 1)[1].splitlines()[0].strip())
            self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)
            index = json.loads((workspace / "index.json").read_text(encoding="utf-8"))
            child = index["pages"][1]
            retained = workspace / child["html"]
            self.assertTrue(retained.is_file())
            self.assertGreater(retained.stat().st_size, 0)
            self.assertEqual(child["stored_bytes"], retained.stat().st_size)

    def test_robots_redirect_chain_shares_one_policy_size_limit(self) -> None:
        entry = b'<html><body><a href="/child">Child</a></body></html>'
        redirect_body = b"#" * (300 * 1024)
        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (
                302,
                {"Content-Type": "text/plain", "Location": "/robots-hop"},
                redirect_body,
            ),
            "/robots-hop": (
                302,
                {"Content-Type": "text/plain", "Location": "/robots-final"},
                redirect_body,
            ),
            "/robots-final": (
                200,
                {"Content-Type": "text/plain"},
                b"User-agent: *\nAllow: /\n",
            ),
            "/child": (
                200,
                {"Content-Type": "text/html"},
                b"<html><body>must not be requested</body></html>",
            ),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "robots-redirect.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                server.requests,
                ["/entry", "/robots.txt", "/robots-hop"],
            )
            self.assertIn("Robots policy exceeded the 512 KiB limit", result.stdout)
            self.assertIn("Fetched 1; skipped 1; failed 0.", result.stdout)

    def test_unreachable_or_oversized_robots_policy_stops_children_successfully(self) -> None:
        entry = b'<html><body><a href="/child">Child</a></body></html>'
        cases = {
            "server-error": (503, {"Content-Type": "text/plain"}, b"unavailable"),
            "oversized": (
                200,
                {"Content-Type": "text/plain"},
                b"User-agent: *\n" + b"#" * (512 * 1024),
            ),
        }
        for name, robots_response in cases.items():
            with self.subTest(name=name), RecordingServer(
                {
                    "/entry": (200, {"Content-Type": "text/html"}, entry),
                    "/robots.txt": robots_response,
                    "/child": (
                        200,
                        {"Content-Type": "text/html"},
                        b"<html><body>child</body></html>",
                    ),
                }
            ) as server, tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "robots.md"

                result = self.run_site2md(
                    "build",
                    f"{server.origin}/entry",
                    "--mode",
                    "follow",
                    "--follow-selector",
                    "a",
                    "--output",
                    output,
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(server.requests, ["/entry", "/robots.txt"])
                self.assertIn("child traversal stopped", result.stdout)
                self.assertIn(f"<!-- Source: {server.origin}/entry -->", output.read_text())

    def test_keep_temp_retains_follow_artifacts_and_debugging_index(self) -> None:
        entry = b'<html><body><a href="/good">Good</a><a href="/large">Large</a></body></html>'

        def stream_large(handler: BaseHTTPRequestHandler) -> None:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html")
            handler.end_headers()
            try:
                for _ in range(20):
                    handler.wfile.write(b"x" * 65536)
                    handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/good": (
                200,
                {"Content-Type": "text/html"},
                b"<html><body>good child</body></html>",
            ),
            "/large": stream_large,
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "follow.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--max-page-size-mib",
                "1",
                "--keep-temp",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            marker = "Temporary files kept at "
            workspace = Path(result.stdout.split(marker, 1)[1].splitlines()[0].strip())
            self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)
            for filename in (
                "page.html",
                "converted.md",
                "page-0001.html",
                "converted-0001.md",
                "page-0002.html",
                "index.json",
            ):
                self.assertTrue((workspace / filename).is_file(), filename)
            self.assertGreater((workspace / "page-0002.html").stat().st_size, 0)
            index = json.loads((workspace / "index.json").read_text(encoding="utf-8"))
            self.assertIn("no compatibility guarantees", index["notice"])
            self.assertEqual(
                [page["requested_url"] for page in index["pages"]],
                [
                    f"{server.origin}/entry",
                    f"{server.origin}/good",
                    f"{server.origin}/large",
                ],
            )
            self.assertEqual(
                [page["status"] for page in index["pages"]],
                ["converted", "converted", "failed"],
            )

    def test_keep_temp_retains_index_for_fatal_partial_entry_retrieval(self) -> None:
        def stream_entry(handler: BaseHTTPRequestHandler) -> None:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html")
            handler.end_headers()
            try:
                for _ in range(20):
                    handler.wfile.write(b"x" * 65536)
                    handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        with RecordingServer(
            {"/entry": stream_entry}
        ) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "entry-failure.md"
            output.write_text("previous", encoding="utf-8")

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--max-page-size-mib",
                "1",
                "--keep-temp",
                "--output",
                output,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "previous")
            marker = "Temporary files kept at "
            workspace = Path(result.stdout.split(marker, 1)[1].splitlines()[0].strip())
            self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)
            self.assertGreater((workspace / "page.html").stat().st_size, 0)
            index = json.loads((workspace / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["pages"][0]["requested_url"], f"{server.origin}/entry")
            self.assertEqual(index["pages"][0]["status"], "failed")
            self.assertGreater(index["pages"][0]["body_bytes"], 0)

    def test_keep_temp_retains_index_for_interrupted_partial_child(self) -> None:
        entry = b'<html><body><a href="/child">Child</a></body></html>'
        routes = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/child": (200, {"Content-Type": "text/html"}, b"<html><body>child</body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "child-interruption.md"
            output.write_text("previous", encoding="utf-8")
            environment = self.startup_hook_environment(
                root,
                """from pathlib import Path
from site2md import remote_build

real_fetch = remote_build.fetch_remote
calls = 0

def interrupt_child(*args, **kwargs):
    global calls
    calls += 1
    if calls == 2:
        Path(kwargs["content_path"]).write_bytes(b"partial child")
        raise KeyboardInterrupt()
    return real_fetch(*args, **kwargs)

remote_build.fetch_remote = interrupt_child
""",
            )

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--keep-temp",
                "--output",
                output,
                extra_environment=environment,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(server.requests, ["/entry", "/robots.txt"])
            self.assertEqual(output.read_text(encoding="utf-8"), "previous")
            marker = "Temporary files kept at "
            workspace = Path(result.stdout.split(marker, 1)[1].splitlines()[0].strip())
            self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)
            index = json.loads((workspace / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index["pages"]), 2)
            self.assertEqual(index["pages"][1]["requested_url"], f"{server.origin}/child")
            self.assertEqual(index["pages"][1]["status"], "interrupted")
            self.assertEqual(index["pages"][1]["html"], "page-0001.html")
            self.assertEqual(index["pages"][1]["stored_bytes"], len(b"partial child"))

    def test_final_entry_origin_and_child_redirect_identity_bound_following(self) -> None:
        entry = b"""<html><body>
<a href="/alias">Alias</a><a href="/final">Final duplicate</a><a href="/escape">Escape</a>
</body></html>"""
        final_body = b"<html><body>final child</body></html>"
        start_routes: dict[str, Route] = {}
        with RecordingServer(start_routes) as start_server:
            child_routes = {
                "/entry": (200, {"Content-Type": "text/html"}, entry),
                "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
                "/alias": (302, {"Location": "/final"}, b""),
                "/final": (200, {"Content-Type": "text/html"}, final_body),
                "/escape": (302, {"Location": f"{start_server.origin}/outside"}, b""),
            }
            with RecordingServer(child_routes) as final_server:
                start_routes.update(
                    {
                        "/start": (302, {"Location": f"{final_server.origin}/entry"}, b""),
                        "/outside": (
                            200,
                            {"Content-Type": "text/html"},
                            b"<html><body>outside</body></html>",
                        ),
                    }
                )
                with tempfile.TemporaryDirectory() as temp_dir:
                    output = Path(temp_dir) / "redirects.md"

                    result = self.run_site2md(
                        "build",
                        f"{start_server.origin}/start",
                        "--mode",
                        "follow",
                        "--follow-selector",
                        "a",
                        "--output",
                        output,
                    )

                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(start_server.requests, ["/start"])
                    self.assertEqual(
                        final_server.requests,
                        ["/entry", "/robots.txt", "/alias", "/final", "/final", "/escape"],
                    )
                    markdown = output.read_text(encoding="utf-8")
                    self.assertEqual(
                        markdown.count(f"<!-- Source: {final_server.origin}/final -->"),
                        1,
                    )
                    self.assertNotIn("outside</", markdown)
                    self.assertIn("Fetched 2; skipped 2; failed 0.", result.stdout)

    def test_expected_child_failures_warn_then_write_successful_pages(self) -> None:
        entry = b"""<html><body>
<a href="/missing">Missing</a><a href="/json">JSON</a>
<a href="/huge">Huge</a><a href="/good">Good</a>
</body></html>"""
        routes = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/missing": (404, {"Content-Type": "text/html"}, b"missing"),
            "/json": (200, {"Content-Type": "application/json"}, b"{}"),
            "/huge": (
                200,
                {"Content-Type": "text/html", "Content-Length": str(2 * 1024 * 1024)},
                b"<html><body>huge</body></html>",
            ),
            "/good": (200, {"Content-Type": "text/html"}, b"<html><body>good</body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "partial-success.md"

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--max-page-size-mib",
                "1",
                "--output",
                output,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                server.requests,
                ["/entry", "/robots.txt", "/missing", "/json", "/huge", "/good"],
            )
            self.assertIn("Fetched 2; skipped 0; failed 3.", result.stdout)
            self.assertLess(result.stdout.index("Warning:"), result.stdout.index("Fetched 2"))
            markdown = output.read_text(encoding="utf-8")
            self.assertIn(f"<!-- Source: {server.origin}/good -->", markdown)
            self.assertNotIn(f"<!-- Source: {server.origin}/missing -->", markdown)

    def test_child_conversion_failure_is_nonfatal_and_preserves_ordered_successes(self) -> None:
        entry = b'<html><body><a href="/bad">Bad</a><a href="/good">Good</a></body></html>'
        routes = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/bad": (200, {"Content-Type": "text/html"}, b"<html><body>bad</body></html>"),
            "/good": (200, {"Content-Type": "text/html"}, b"<html><body>good</body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "partial-success.md"
            environment = self.startup_hook_environment(
                root,
                """from site2md import remote_build

real_convert = remote_build.convert_remote_page_to_markdown

def convert(page):
    if page.source_url.endswith("/bad"):
        raise RuntimeError("forced child conversion failure")
    return real_convert(page)

remote_build.convert_remote_page_to_markdown = convert
""",
            )

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--output",
                output,
                extra_environment=environment,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("forced child conversion failure", " ".join(result.stdout.split()))
            self.assertIn("Fetched 2; skipped 0; failed 1.", result.stdout)
            markdown = output.read_text(encoding="utf-8")
            self.assertNotIn(f"<!-- Source: {server.origin}/bad -->", markdown)
            self.assertIn(f"<!-- Source: {server.origin}/good -->", markdown)

    def test_multi_source_follow_document_remains_extractable_with_provenance(self) -> None:
        entry = b"""<html><body><a href="/second">Second</a>
<h3>Firstland</h3><p><strong>Capital:</strong> First City<br>
<strong>Population:</strong> 10<br><strong>Area (km2):</strong> 20</p>
</body></html>"""
        child = b"""<html><body>
<h3>Secondland</h3><p><strong>Capital:</strong> Second City<br>
<strong>Population:</strong> 30<br><strong>Area (km2):</strong> 40</p>
</body></html>"""
        routes = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/second": (200, {"Content-Type": "text/html"}, child),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            markdown_path = root / "countries.md"

            build_result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--output",
                markdown_path,
            )
            extract_result = self.run_site2md(
                "extract",
                "site2md.scrapethissite.countries",
                markdown_path,
            )

            self.assertEqual(build_result.returncode, 0, build_result.stdout + build_result.stderr)
            self.assertEqual(extract_result.returncode, 0, extract_result.stdout + extract_result.stderr)
            payload = json.loads(extract_result.stdout)
            self.assertEqual(
                [record["value"]["name"] for record in payload["records"]],
                ["Firstland", "Secondland"],
            )
            self.assertEqual(
                [record["provenance"]["source"] for record in payload["records"]],
                [f"{server.origin}/entry", f"{server.origin}/second"],
            )

    def test_follow_interruption_preserves_destination_and_cleans_workspace(self) -> None:
        entry = b'<html><body><a href="/one">One</a><a href="/two">Two</a></body></html>'
        routes = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/one": (200, {"Content-Type": "text/html"}, b"<html><body>one</body></html>"),
            "/two": (200, {"Content-Type": "text/html"}, b"<html><body>two</body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace_root = root / "workspaces"
            workspace_root.mkdir()
            output = root / "result.md"
            output.write_text("previous", encoding="utf-8")
            environment = self.startup_hook_environment(
                root,
                """from site2md import downloader

def interrupt(_seconds):
    raise KeyboardInterrupt()

downloader.time.sleep = interrupt
""",
            )
            environment["TMPDIR"] = str(workspace_root)

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "follow",
                "--follow-selector",
                "a",
                "--output",
                output,
                extra_environment=environment,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(server.requests, ["/entry", "/robots.txt", "/one"])
            self.assertEqual(output.read_text(encoding="utf-8"), "previous")
            self.assertEqual(list(workspace_root.iterdir()), [])
            self.assertIn("Remote build interrupted", result.stdout)


if __name__ == "__main__":
    unittest.main()
