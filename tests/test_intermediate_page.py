"""Installed-command tests that build refuses an intermediate page: a redirect to a sign-in or a browser check."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler
from itertools import pairwise
from pathlib import Path

from tests.browser_test_support import BrowserTestCase
from tests.cli_test_support import (
    SKIP_PACING_HOOK,
    InstalledCliTestCase,
    RecordingServer,
    Route,
    respond,
)

HTML = {"Content-Type": "text/html"}
TEXT = {"Content-Type": "text/plain"}
INDEX = b'<html><body><main><h1>Index</h1><a href="/articles/one">One</a> <a href="/articles/two">Two</a></main></body></html>'
FOLLOW_INDEX = b'<html><body><main><h1>Index</h1><a href="/articles/one">One</a> <a href="/articles/ok">Ok</a></main></body></html>'
SIGN_IN = (
    b"<html><head><title>Sign in</title></head><body><main><h1>Sign in to continue</h1>"
    b'<p>Enter your name and password.</p><a href="/forgot">Forgot your password?</a></main></body></html>'
)
ARTICLE = b"<html><body><main><h1>Article</h1><p>The real text.</p></main></body></html>"
# Rich wraps a message at 80 columns unless told otherwise, and these messages hold two URLs.
WIDE = {"COLUMNS": "500"}
PROGRESS_BARS = ("Converting HTML to Markdown...", "Building remote page...")
FOLLOW_ARGUMENTS = ("--mode", "follow", "--follow-selector", "a")
# The final URLs whose query holds the requested address, as the rule reads it, and what was requested.
CARRYING_THE_REQUESTED_ADDRESS = (
    ("its path", "/articles/one", "/login?return_to=%2Farticles%2Fone"),
    ("its path and query", "/articles/one?ref=a", "/login?return_to=%2Farticles%2Fone%3Fref%3Da"),
    ("the whole URL, among other parameters", "/articles/one", "/login?lang=en&next={origin}%2Farticles%2Fone"),
    ("its path, where the requested URL has a fragment", "/articles/one#top", "/login?return_to=%2Farticles%2Fone"),
)
# What was requested, and where it is redirected, for redirects that don't carry the requested address.
ORDINARY_REDIRECTS = (
    ("a query that holds no address", "/old", "/new?utm=campaign"),
    ("a parameter that holds another address", "/old", "/new?return_to=%2Felsewhere"),
    ("a parameter that holds a part of the path", "/articles/one", "/new?from=%2Farticles"),
)


def sign_in_routes(*names: str) -> dict[str, Route]:
    """Serve an index, no robots policy, and articles that are each redirected to a sign-in page that returns to them."""
    routes: dict[str, Route] = {
        "/": (200, HTML, INDEX),
        "/robots.txt": (404, TEXT, b"missing"),
    }
    for name in names:
        routes[f"/articles/{name}"] = (302, {"Location": f"/login?return_to=%2Farticles%2F{name}"}, b"")
        routes[f"/login?return_to=%2Farticles%2F{name}"] = (200, HTML, SIGN_IN)
    return routes


def refusal(origin: str, name: str) -> str:
    """Return the reason that build gives for an article that was redirected to its sign-in page."""
    return (
        f"Redirected from {origin}/articles/{name} to {origin}/login?return_to=%2Farticles%2F{name}, "
        "an intermediate page such as a sign-in or a browser check."
    )


class IntermediatePageTests(InstalledCliTestCase):
    """A redirect to a page that stands in front of the requested one is a failure, not the content."""

    def run_build(
        self, *arguments: object, extra_environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run build without the progress bar and with lines wide enough to stay whole."""
        result = self.run_site2md(
            "build", *arguments, "--no-progress", extra_environment={**WIDE, **(extra_environment or {})}
        )
        self.assertNotIn("Traceback", result.stderr)
        return result

    def run_build_both_ways(
        self, *arguments: object, returncode: int, environment: dict[str, str]
    ) -> list[str]:
        """Build with and without the progress bar, and return the lines that both runs print."""
        with_bar = self.run_site2md("build", *arguments, extra_environment=environment)
        without_bar = self.run_site2md("build", *arguments, "--no-progress", extra_environment=environment)
        for result in (with_bar, without_bar):
            self.assertEqual(result.returncode, returncode, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)
        lines = [
            line for line in with_bar.stdout.splitlines() if not any(bar in line for bar in PROGRESS_BARS)
        ]
        self.assertEqual(without_bar.stdout.splitlines(), lines)
        return lines

    def test_page_build_fails_when_the_entry_page_redirects_to_a_sign_in_page(self) -> None:
        with RecordingServer(sign_in_routes("one", "two")) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "one.md"
            output.write_text("previous", encoding="utf-8")

            result = self.run_build(f"{server.origin}/articles/one", "--output", output)

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(
                result.stdout.splitlines(),
                [f"Error fetching remote page: {refusal(server.origin, 'one')}"],
            )
            self.assertEqual(output.read_text(encoding="utf-8"), "previous")
            self.assertEqual(server.requests, ["/articles/one", "/login?return_to=%2Farticles%2Fone"])

    def test_a_build_that_fails_on_an_intermediate_page_writes_no_file(self) -> None:
        with RecordingServer(sign_in_routes("one")) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "one.md"

            result = self.run_build(f"{server.origin}/articles/one", "--output", output)

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_the_entry_page_fails_in_every_remote_mode(self) -> None:
        modes = {"page": (), "follow": FOLLOW_ARGUMENTS, "site": ("--mode", "site")}
        with RecordingServer(sign_in_routes("one")) as server, tempfile.TemporaryDirectory() as temp_dir:
            for mode, arguments in modes.items():
                with self.subTest(mode=mode):
                    output = Path(temp_dir) / f"{mode}.md"
                    output.write_text("previous", encoding="utf-8")

                    result = self.run_build(f"{server.origin}/articles/one", *arguments, "--output", output)

                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertEqual(
                        result.stdout.splitlines(),
                        [f"Error fetching remote page: {refusal(server.origin, 'one')}"],
                    )
                    self.assertEqual(output.read_text(encoding="utf-8"), "previous")
            self.assertNotIn("/robots.txt", server.requests)

    def test_site_build_warns_for_each_redirected_child_and_counts_it_as_failed(self) -> None:
        with RecordingServer(sign_in_routes("one", "two")) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "site.md"

            result = self.run_build(
                f"{server.origin}/",
                "--mode",
                "site",
                "--output",
                output,
                extra_environment=self.startup_hook_environment(root, SKIP_PACING_HOOK),
            )

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(
                result.stdout.splitlines(),
                [
                    f"Warning: Could not fetch {server.origin}/articles/one: {refusal(server.origin, 'one')}",
                    f"Warning: Could not fetch {server.origin}/articles/two: {refusal(server.origin, 'two')}",
                    "Fetched 1; skipped 0; failed 2.",
                    f"Success! Markdown created at {output}",
                ],
            )
            markdown = output.read_text(encoding="utf-8")
            self.assertIn("# Index", markdown)
            self.assertNotIn("Sign in", markdown)
            self.assertEqual(markdown.count("<!-- Source:"), 1)
            # The traversal went on to the second child, and took no link from a sign-in page.
            self.assertEqual(
                server.requests,
                [
                    "/",
                    "/robots.txt",
                    "/articles/one",
                    "/login?return_to=%2Farticles%2Fone",
                    "/articles/two",
                    "/login?return_to=%2Farticles%2Ftwo",
                ],
            )

    def test_follow_build_skips_a_redirected_child_and_converts_the_next(self) -> None:
        routes = {**sign_in_routes("one"), "/": (200, HTML, FOLLOW_INDEX), "/articles/ok": (200, HTML, ARTICLE)}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "follow.md"

            result = self.run_build(
                f"{server.origin}/",
                *FOLLOW_ARGUMENTS,
                "--output",
                output,
                extra_environment=self.startup_hook_environment(root, SKIP_PACING_HOOK),
            )

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(
                result.stdout.splitlines(),
                [
                    f"Warning: Could not fetch {server.origin}/articles/one: {refusal(server.origin, 'one')}",
                    "Fetched 2; skipped 0; failed 1.",
                    f"Success! Markdown created at {output}",
                ],
            )
            markdown = output.read_text(encoding="utf-8")
            self.assertIn("The real text.", markdown)
            self.assertNotIn("Sign in", markdown)
            self.assertEqual(markdown.count("<!-- Source:"), 2)

    def test_a_redirected_child_uses_up_a_place_in_the_page_budget(self) -> None:
        routes = {**sign_in_routes("one"), "/": (200, HTML, FOLLOW_INDEX), "/articles/ok": (200, HTML, ARTICLE)}
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "follow.md"

            result = self.run_build(
                f"{server.origin}/",
                *FOLLOW_ARGUMENTS,
                "--max-pages",
                "2",
                "--output",
                output,
                extra_environment=self.startup_hook_environment(root, SKIP_PACING_HOOK),
            )

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(
                result.stdout.splitlines(),
                [
                    f"Warning: Could not fetch {server.origin}/articles/one: {refusal(server.origin, 'one')}",
                    "Reached limit: page count (2)",
                    "Fetched 1; skipped 0; failed 1.",
                    f"Success! Markdown created at {output}",
                ],
            )
            self.assertNotIn("/articles/ok", server.requests)

    def test_a_redirected_child_is_followed_by_the_request_delay(self) -> None:
        asked_at: list[float] = []

        def redirect_to_sign_in(name: str) -> Route:
            def route(handler: BaseHTTPRequestHandler) -> None:
                asked_at.append(time.perf_counter())
                respond(handler, (302, {"Location": f"/login?return_to=%2Farticles%2F{name}"}, b""))

            return route

        routes = {
            **sign_in_routes("one", "two"),
            "/articles/one": redirect_to_sign_in("one"),
            "/articles/two": redirect_to_sign_in("two"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "follow.md"

            result = self.run_build(f"{server.origin}/", *FOLLOW_ARGUMENTS, "--output", output)

            self.assertEqual(result.returncode, 0, result.stdout)
            gaps = [later - earlier for earlier, later in pairwise(asked_at)]
            self.assertEqual(len(gaps), 1)
            # Without a robots policy the delay is the one-second default, and the server must never see less.
            self.assertGreaterEqual(gaps[0], 1.0)

    def test_a_final_url_that_carries_the_requested_address_is_an_intermediate_page(self) -> None:
        for label, requested, template in CARRYING_THE_REQUESTED_ADDRESS:
            with self.subTest(label):
                routes: dict[str, Route] = {}
                with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
                    final = template.replace("{origin}", urllib.parse.quote(server.origin, safe=""))
                    routes[requested.split("#")[0]] = (302, {"Location": final}, b"")
                    routes[final] = (200, HTML, SIGN_IN)
                    output = Path(temp_dir) / "out.md"

                    result = self.run_build(f"{server.origin}{requested}", "--output", output)

                    self.assertEqual(result.returncode, 1, result.stdout)
                    expected = (
                        f"Error fetching remote page: Redirected from {server.origin}{requested} "
                        f"to {server.origin}{final}, an intermediate page such as a sign-in or a browser check."
                    )
                    self.assertEqual(result.stdout.splitlines(), [expected])
                    self.assertFalse(output.exists())

    def test_a_redirect_that_does_not_carry_the_requested_address_still_succeeds(self) -> None:
        for label, requested, final in ORDINARY_REDIRECTS:
            with self.subTest(label):
                routes: dict[str, Route] = {
                    requested: (302, {"Location": final}, b""),
                    final: (200, HTML, ARTICLE),
                }
                with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
                    output = Path(temp_dir) / "out.md"

                    result = self.run_build(f"{server.origin}{requested}", "--output", output)

                    self.assertEqual(result.returncode, 0, result.stdout)
                    self.assertEqual(server.requests, [requested, final])
                    markdown = output.read_text(encoding="utf-8")
                    self.assertIn(f"<!-- Source: {server.origin}{final} -->", markdown)
                    self.assertIn("The real text.", markdown)

    def test_a_page_that_names_its_own_address_and_was_not_redirected_still_succeeds(self) -> None:
        requested = "/article?back=%2Farticle"
        with RecordingServer({requested: (200, HTML, ARTICLE)}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "out.md"

            result = self.run_build(f"{server.origin}{requested}", "--output", output)

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("The real text.", output.read_text(encoding="utf-8"))

    def test_the_messages_are_the_same_lines_with_and_without_a_progress_bar(self) -> None:
        with RecordingServer(sign_in_routes("one", "two")) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "out.md"
            environment = {**WIDE, **self.startup_hook_environment(root, SKIP_PACING_HOOK)}

            entry_lines = self.run_build_both_ways(
                f"{server.origin}/articles/one", "--output", output, returncode=1, environment=environment
            )
            site_lines = self.run_build_both_ways(
                f"{server.origin}/", "--mode", "site", "--output", output, returncode=0, environment=environment
            )

            self.assertEqual(entry_lines, [f"Error fetching remote page: {refusal(server.origin, 'one')}"])
            self.assertEqual(
                site_lines,
                [
                    f"Warning: Could not fetch {server.origin}/articles/one: {refusal(server.origin, 'one')}",
                    f"Warning: Could not fetch {server.origin}/articles/two: {refusal(server.origin, 'two')}",
                    "Fetched 1; skipped 0; failed 2.",
                    f"Success! Markdown created at {output}",
                ],
            )

    def test_keep_temp_keeps_the_intermediate_page_and_records_the_failure(self) -> None:
        with RecordingServer(sign_in_routes("one")) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "one.md"

            result = self.run_build(f"{server.origin}/articles/one", "--keep-temp", "--output", output)

            self.assertEqual(result.returncode, 1, result.stdout)
            workspace = self.retained_workspace(result.stdout)
            self.assertIn("Sign in to continue", (workspace / "page.html").read_text(encoding="utf-8"))
            page = json.loads((workspace / "index.json").read_text(encoding="utf-8"))["pages"][0]
            self.assertEqual(page["status"], "failed")
            self.assertEqual(page["detail"], refusal(server.origin, "one"))


class BrowserIntermediatePageTests(BrowserTestCase):
    """The same refusal when the page is read from a browser that a redirect sent to a sign-in page."""

    def test_a_browser_that_is_sent_to_a_sign_in_page_fails_the_build(self) -> None:
        with RecordingServer(sign_in_routes("one")) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "one.md"
            output.write_text("previous", encoding="utf-8")

            result = self.run_site2md(
                "build",
                f"{server.origin}/articles/one",
                "--browser",
                "--output",
                output,
                "--no-progress",
                timeout=90,
                extra_environment=WIDE,
            )

            self.assert_failed_without_replacing_output(result, output)
            self.assertEqual(
                result.stdout.splitlines(),
                [f"Error fetching remote page: {refusal(server.origin, 'one')}"],
            )


if __name__ == "__main__":
    unittest.main()
