"""Installed-command acceptance tests for bounded site mode."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_cli import RecordingServer, Route


class SiteModeCliTests(unittest.TestCase):
    """Exercise site mode through the installed command and real HTTP."""

    command: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.command = Path(sys.executable).with_name("site2md")
        if not cls.command.is_file():
            raise RuntimeError(f"Installed site2md command not found at {cls.command}")

    def run_site2md(
        self,
        *arguments: object,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the installed command and capture its observable result."""
        environment = os.environ.copy()
        if extra_environment:
            environment.update(extra_environment)
        return subprocess.run(
            [str(self.command), *map(str, arguments)],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    @staticmethod
    def startup_hook_environment(root: Path, source: str) -> dict[str, str]:
        """Create a subprocess-only Python startup hook."""
        hook_dir = root / "startup-hook"
        hook_dir.mkdir()
        (hook_dir / "sitecustomize.py").write_text(source, encoding="utf-8")
        python_path = os.environ.get("PYTHONPATH")
        hook_path = (
            f"{hook_dir}{os.pathsep}{python_path}" if python_path else str(hook_dir)
        )
        return {"PYTHONPATH": hook_path}

    def test_site_mode_discovers_same_origin_pages_in_breadth_first_order(self) -> None:
        entry = b"""<html><head>
<link rel="canonical" href="https://example.invalid/elsewhere">
</head><body><nav>
<a href="/branch-b">Branch B</a>
<a href="/branch-a">Branch A</a>
<a href="/branch-b#duplicate">Branch B duplicate</a>
<a href="/filtered?b=2&a=1">Filtered</a>
<a href="/hidden" rel="external nofollow">Hidden</a>
<a href="https://example.invalid/external">External</a>
</nav><main>Entry</main></body></html>"""
        branch_b = b"""<html><body><main>Branch B
<a href="/leaf-b">Leaf B</a><a href="/shared">Shared</a>
<a href="/entry">Cycle</a>
</main></body></html>"""
        branch_a = b"""<html><head><base href="/base/"></head><body><main>Branch A
<a href="leaf-a">Leaf A</a><a href="/shared#duplicate">Shared duplicate</a>
</main></body></html>"""
        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/branch-b": (200, {"Content-Type": "text/html"}, branch_b),
            "/branch-a": (200, {"Content-Type": "text/html"}, branch_a),
            "/leaf-b": (200, {"Content-Type": "text/html"}, b"<html><body>Leaf B</body></html>"),
            "/shared": (200, {"Content-Type": "text/html"}, b"<html><body>Shared</body></html>"),
            "/base/leaf-a": (200, {"Content-Type": "text/html"}, b"<html><body>Leaf A</body></html>"),
            "/filtered?b=2&a=1": (200, {"Content-Type": "text/html"}, b"<html><body>Filtered</body></html>"),
            "/hidden": (200, {"Content-Type": "text/html"}, b"<html><body>Hidden</body></html>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "site.md"
            environment = self.startup_hook_environment(
                root,
                """from site2md import downloader
downloader.time.sleep = lambda _seconds: None
""",
            )

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "site",
                "--output",
                output,
                extra_environment=environment,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                server.requests,
                [
                    "/entry",
                    "/robots.txt",
                    "/branch-b",
                    "/branch-a",
                    "/leaf-b",
                    "/shared",
                    "/base/leaf-a",
                ],
            )
            markdown = output.read_text(encoding="utf-8")
            sources = [
                f"<!-- Source: {server.origin}{path} -->"
                for path in (
                    "/entry",
                    "/branch-b",
                    "/branch-a",
                    "/leaf-b",
                    "/shared",
                    "/base/leaf-a",
                )
            ]
            positions = [markdown.index(source) for source in sources]
            self.assertEqual(positions, sorted(positions))
            self.assertNotIn("Filtered", markdown)
            self.assertNotIn("Hidden", markdown)
            self.assertIn("Fetched 6; skipped 0; failed 0.", result.stdout)

    def test_query_opt_in_preserves_query_and_depth_limit_bounds_discovery(self) -> None:
        routes: dict[str, Route] = {
            "/entry": (
                200,
                {"Content-Type": "text/html"},
                b'<html><body><a href="/depth-one?b=2&a=1">One</a></body></html>',
            ),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/depth-one?b=2&a=1": (
                200,
                {"Content-Type": "text/html"},
                b'<html><body>One<a href="/depth-two">Two</a></body></html>',
            ),
            "/depth-two": (
                200,
                {"Content-Type": "text/html"},
                b'<html><body>Two<a href="/depth-three">Three</a></body></html>',
            ),
            "/depth-three": (
                200,
                {"Content-Type": "text/html"},
                b"<html><body>Three</body></html>",
            ),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "bounded.md"
            environment = self.startup_hook_environment(
                root,
                """from site2md import downloader
downloader.time.sleep = lambda _seconds: None
""",
            )

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "site",
                "--include-query",
                "--max-depth",
                "2",
                "--output",
                output,
                extra_environment=environment,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                server.requests,
                [
                    "/entry",
                    "/robots.txt",
                    "/depth-one?b=2&a=1",
                    "/depth-two",
                ],
            )
            markdown = output.read_text(encoding="utf-8")
            self.assertIn(
                f"<!-- Source: {server.origin}/depth-one?b=2&a=1 -->",
                markdown,
            )
            self.assertNotIn(f"<!-- Source: {server.origin}/depth-three -->", markdown)
            self.assertIn("Reached limit: depth (2)", result.stdout)

    def test_default_depth_is_three(self) -> None:
        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, b'<a href="/one">One</a>'),
            "/robots.txt": (404, {"Content-Type": "text/plain"}, b"missing"),
            "/one": (200, {"Content-Type": "text/html"}, b'<a href="/two">Two</a>'),
            "/two": (200, {"Content-Type": "text/html"}, b'<a href="/three">Three</a>'),
            "/three": (200, {"Content-Type": "text/html"}, b'<a href="/four">Four</a>'),
            "/four": (200, {"Content-Type": "text/html"}, b"<p>Four</p>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "default-depth.md"
            environment = self.startup_hook_environment(
                root,
                """from site2md import downloader
downloader.time.sleep = lambda _seconds: None
""",
            )

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "site",
                "--output",
                output,
                extra_environment=environment,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                server.requests,
                ["/entry", "/robots.txt", "/one", "/two", "/three"],
            )
            self.assertIn("Reached limit: depth (3)", result.stdout)
            self.assertNotIn(
                f"<!-- Source: {server.origin}/four -->",
                output.read_text(encoding="utf-8"),
            )

    def test_site_mode_rejects_incompatible_options_before_network_access(self) -> None:
        with RecordingServer({}) as server, tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.md"
            cases = (
                ("--mode", "site", "--follow-selector", "a"),
                ("--mode", "page", "--max-depth", "1"),
                ("--mode", "follow", "--follow-selector", "a", "--max-depth", "1"),
                ("--mode", "page", "--include-query"),
                ("--mode", "follow", "--follow-selector", "a", "--include-query"),
                ("--mode", "site", "--max-depth", "0"),
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
                    self.assertFalse(output.exists())

            local_root = Path(temp_dir) / "local"
            local_root.mkdir()
            local_result = self.run_site2md(
                "build",
                local_root,
                "--include-query",
                "--output",
                output,
            )
            self.assertNotEqual(local_result.returncode, 0)
            self.assertFalse(output.exists())

    def test_shared_page_budget_counts_failures_robots_and_redirect_duplicates(self) -> None:
        entry = b"""<html><body>
<a href="/blocked">Blocked</a><a href="/missing">Missing</a>
<a href="/alias">Alias</a><a href="/final">Final</a>
<a href="/branch">Branch</a>
</body></html>"""
        routes: dict[str, Route] = {
            "/entry": (200, {"Content-Type": "text/html"}, entry),
            "/robots.txt": (
                200,
                {"Content-Type": "text/plain"},
                b"User-agent: *\nDisallow: /blocked\n",
            ),
            "/missing": (404, {"Content-Type": "text/html"}, b"missing"),
            "/alias": (302, {"Location": "/final"}, b""),
            "/final": (200, {"Content-Type": "text/html"}, b"<p>Final</p>"),
            "/branch": (
                200,
                {"Content-Type": "text/html"},
                b'<p>Branch</p><a href="/deeper">Deeper</a>',
            ),
            "/deeper": (200, {"Content-Type": "text/html"}, b"<p>Deeper</p>"),
        }
        with RecordingServer(routes) as server, tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "budget.md"
            environment = self.startup_hook_environment(
                root,
                """from site2md import downloader
downloader.time.sleep = lambda _seconds: None
""",
            )

            result = self.run_site2md(
                "build",
                f"{server.origin}/entry",
                "--mode",
                "site",
                "--max-pages",
                "6",
                "--output",
                output,
                extra_environment=environment,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                server.requests,
                [
                    "/entry",
                    "/robots.txt",
                    "/missing",
                    "/alias",
                    "/final",
                    "/final",
                    "/branch",
                ],
            )
            markdown = output.read_text(encoding="utf-8")
            self.assertEqual(
                markdown.count(f"<!-- Source: {server.origin}/final -->"),
                1,
            )
            self.assertNotIn(f"<!-- Source: {server.origin}/deeper -->", markdown)
            self.assertIn("Robots policy disallows", result.stdout)
            self.assertIn("Could not fetch", result.stdout)
            self.assertIn("Reached limit: page count (6)", result.stdout)
            self.assertIn("Fetched 3; skipped 2; failed 1.", result.stdout)


if __name__ == "__main__":
    unittest.main()
